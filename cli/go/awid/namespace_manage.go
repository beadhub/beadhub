package awid

import (
	"context"
	"fmt"
	"strings"
)

// ExternalNamespaceRequest is sent to the project-scoped hosted namespace route.
type ExternalNamespaceRequest struct {
	Domain     string `json:"domain"`
	OwnerType  string `json:"owner_type,omitempty"`
	OwnerOrgID string `json:"owner_org_id,omitempty"`
}

// NamespaceSummary is returned by namespace management endpoints.
type NamespaceSummary struct {
	NamespaceID           string `json:"namespace_id"`
	Slug                  string `json:"slug"`
	FullName              string `json:"full_name"`
	DisplayName           string `json:"display_name"`
	IsDefault             bool   `json:"is_default"`
	IsExternal            bool   `json:"is_external"`
	AssignedIdentityCount int    `json:"assigned_identity_count"`
	PublishedAgentCount   int    `json:"published_agent_count,omitempty"`
	DnsTxtName            string `json:"dns_txt_name"`
	DnsTxtValue           string `json:"dns_txt_value"`
	DnsStatus             string `json:"dns_status"`
	RegistrationStatus    string `json:"registration_status"`
	CreatedAt             string `json:"created_at"`
}

func (n NamespaceSummary) IdentityCount() int {
	if n.AssignedIdentityCount != 0 {
		return n.AssignedIdentityCount
	}
	return n.PublishedAgentCount
}

// AddExternalNamespace creates a BYOD namespace for the given project.
func (c *Client) AddExternalNamespace(ctx context.Context, projectID string, req *ExternalNamespaceRequest) (*NamespaceSummary, error) {
	if req.Domain == "" {
		return nil, fmt.Errorf("aweb: domain is required")
	}
	var out NamespaceSummary
	if strings.TrimSpace(projectID) == "" {
		return nil, fmt.Errorf("aweb: project id is required")
	}
	if err := c.Post(ctx, "/api/v1/projects/"+urlPathEscape(projectID)+"/namespaces/external", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// VerifyNamespace triggers DNS verification for a namespace.
func (c *Client) VerifyNamespace(ctx context.Context, projectID, namespaceID string) (*NamespaceSummary, error) {
	var out NamespaceSummary
	if strings.TrimSpace(projectID) == "" {
		return nil, fmt.Errorf("aweb: project id is required")
	}
	if err := c.Post(ctx, "/api/v1/projects/"+urlPathEscape(projectID)+"/namespaces/"+urlPathEscape(namespaceID)+"/verify", nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ListManagedNamespaces returns all namespaces with management details.
func (c *Client) ListManagedNamespaces(ctx context.Context, projectID string) ([]NamespaceSummary, error) {
	var out []NamespaceSummary
	if strings.TrimSpace(projectID) == "" {
		return nil, fmt.Errorf("aweb: project id is required")
	}
	if err := c.Get(ctx, "/api/v1/projects/"+urlPathEscape(projectID)+"/namespaces", &out); err != nil {
		return nil, err
	}
	return out, nil
}

// DeleteNamespace removes a namespace.
func (c *Client) DeleteNamespace(ctx context.Context, projectID, namespaceID string) error {
	if strings.TrimSpace(projectID) == "" {
		return fmt.Errorf("aweb: project id is required")
	}
	return c.Delete(ctx, "/api/v1/projects/"+urlPathEscape(projectID)+"/namespaces/"+urlPathEscape(namespaceID))
}
