package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	aweb "github.com/awebai/aw"
	"github.com/awebai/aw/awid"
	"github.com/spf13/cobra"
)

// resolveCloudClient creates an API-key client for hosted cloud endpoints.
func resolveCloudClient() (*aweb.Client, error) {
	_, sel, err := resolveAPIKeyOnly()
	if err != nil {
		return nil, err
	}
	return aweb.NewWithAPIKey(sel.BaseURL, sel.APIKey)
}

func resolveHostedProjectID(ctx context.Context, client *aweb.Client) (string, error) {
	intro, err := client.Introspect(ctx)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(intro.ProjectID) == "" {
		return "", fmt.Errorf("could not determine project id from the current auth context")
	}
	return strings.TrimSpace(intro.ProjectID), nil
}

var projectNamespaceCmd = &cobra.Command{
	Use:   "namespace",
	Short: "Manage project namespaces",
}

var namespaceAddCmd = &cobra.Command{
	Use:   "add <domain>",
	Short: "Add a BYOD namespace to the current project",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		domain := strings.TrimSpace(args[0])
		if domain == "" {
			return usageError("domain is required")
		}

		client, err := resolveCloudClient()
		if err != nil {
			return err
		}

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		projectID, err := resolveHostedProjectID(ctx, client)
		if err != nil {
			return err
		}

		resp, err := client.AddExternalNamespace(ctx, projectID, &awid.ExternalNamespaceRequest{
			Domain: domain,
		})
		if err != nil {
			return err
		}

		printOutput(resp, func(v any) string {
			r := v.(*awid.NamespaceSummary)
			var b strings.Builder
			fmt.Fprintf(&b, "Domain %s added.\n\n", r.FullName)
			fmt.Fprintf(&b, "Add this DNS TXT record to verify ownership:\n\n")
			fmt.Fprintf(&b, "  Name:  %s\n", r.DnsTxtName)
			fmt.Fprintf(&b, "  Type:  TXT\n")
			fmt.Fprintf(&b, "  Value: %s\n\n", r.DnsTxtValue)
			fmt.Fprintf(&b, "Next:\n")
			fmt.Fprintf(&b, "  1. Add the TXT record in your DNS provider.\n")
			fmt.Fprintf(&b, "  2. Wait for DNS propagation.\n")
			fmt.Fprintf(&b, "  3. Run: aw project namespace verify %s\n\n", r.FullName)
			fmt.Fprintf(&b, "If verification does not succeed immediately, wait a few minutes and run the verify command again.\n")
			return b.String()
		})
		return nil
	},
}

var namespaceVerifyCmd = &cobra.Command{
	Use:   "verify <domain>",
	Short: "Verify DNS and register a BYOD namespace for the current project",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		domain := strings.TrimSpace(args[0])
		if domain == "" {
			return usageError("domain is required")
		}

		client, err := resolveCloudClient()
		if err != nil {
			return err
		}

		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		projectID, err := resolveHostedProjectID(ctx, client)
		if err != nil {
			return err
		}

		ns, err := findNamespaceByDomain(ctx, client, projectID, domain)
		if err != nil {
			return err
		}

		resp, err := client.VerifyNamespace(ctx, projectID, ns.NamespaceID)
		if err != nil {
			code, _ := awid.HTTPStatusCode(err)
			if code == 400 || code == 422 {
				fmt.Printf("DNS verification failed for %s.\n\n", domain)
				fmt.Printf("Make sure the TXT record is set correctly:\n")
				fmt.Printf("  Name:  %s\n", ns.DnsTxtName)
				fmt.Printf("  Type:  TXT\n")
				fmt.Printf("  Value: %s\n\n", ns.DnsTxtValue)
				fmt.Printf("DNS changes can take a few minutes to propagate. Try again shortly.\n")
				return &cliError{code: 1, msg: "DNS verification failed"}
			}
			return err
		}

		printOutput(resp, func(v any) string {
			r := v.(*awid.NamespaceSummary)
			return fmt.Sprintf("DNS verified. Namespace %s registered.\nAgents can now be addressed as %s/<alias>\n", r.FullName, r.FullName)
		})
		return nil
	},
}

var namespaceListCmd = &cobra.Command{
	Use:   "list",
	Short: "List namespaces attached to the current project",
	RunE: func(cmd *cobra.Command, args []string) error {
		client, err := resolveCloudClient()
		if err != nil {
			return err
		}

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		projectID, err := resolveHostedProjectID(ctx, client)
		if err != nil {
			return err
		}

		list, err := client.ListManagedNamespaces(ctx, projectID)
		if err != nil {
			return err
		}

		printOutput(list, func(v any) string {
			items := v.([]awid.NamespaceSummary)
			var b strings.Builder
			fmt.Fprintf(&b, "%-24s %-10s %-14s %s\n", "DOMAIN", "TYPE", "STATUS", "AGENTS")
			for _, ns := range items {
				nsType := "managed"
				if ns.IsExternal {
					nsType = "external"
				}
				fmt.Fprintf(&b, "%-24s %-10s %-14s %d\n", ns.FullName, nsType, ns.RegistrationStatus, ns.IdentityCount())
			}
			return b.String()
		})
		return nil
	},
}

var namespaceDeleteForce bool

var namespaceDeleteCmd = &cobra.Command{
	Use:   "delete <domain>",
	Short: "Delete a namespace from the current project",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		domain := strings.TrimSpace(args[0])
		if domain == "" {
			return usageError("domain is required")
		}

		client, err := resolveCloudClient()
		if err != nil {
			return err
		}

		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		projectID, err := resolveHostedProjectID(ctx, client)
		if err != nil {
			return err
		}

		ns, err := findNamespaceByDomain(ctx, client, projectID, domain)
		if err != nil {
			return err
		}

		if !namespaceDeleteForce {
			if !isTTY() {
				return usageError("--force is required for non-interactive project namespace deletion")
			}
			v, err := promptString(fmt.Sprintf("Delete namespace %s? [y/N]", domain), "N")
			if err != nil {
				return err
			}
			if !strings.EqualFold(strings.TrimSpace(v), "y") {
				fmt.Println("Cancelled.")
				return nil
			}
		}

		if err := client.DeleteNamespace(ctx, projectID, ns.NamespaceID); err != nil {
			return err
		}

		if jsonFlag {
			printJSON(map[string]string{"status": "deleted"})
		} else {
			fmt.Printf("Namespace %s deleted.\n", domain)
		}
		return nil
	},
}

func findNamespaceByDomain(ctx context.Context, client *aweb.Client, projectID, domain string) (*awid.NamespaceSummary, error) {
	list, err := client.ListManagedNamespaces(ctx, projectID)
	if err != nil {
		return nil, err
	}

	for i := range list {
		if strings.EqualFold(list[i].FullName, domain) {
			return &list[i], nil
		}
	}
	return nil, fmt.Errorf("namespace %s not found — run `aw project namespace add` first", domain)
}

func init() {
	namespaceDeleteCmd.Flags().BoolVar(&namespaceDeleteForce, "force", false, "Skip confirmation prompt")

	projectNamespaceCmd.AddCommand(namespaceAddCmd)
	projectNamespaceCmd.AddCommand(namespaceVerifyCmd)
	projectNamespaceCmd.AddCommand(namespaceListCmd)
	projectNamespaceCmd.AddCommand(namespaceDeleteCmd)
	projectCmd.AddCommand(projectNamespaceCmd)
}
