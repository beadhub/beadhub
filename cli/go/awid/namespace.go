package awid

import "context"

// Namespace describes a namespace owned by a user.
type Namespace struct {
	Slug       string `json:"slug"`
	Tier       string `json:"tier"`
	AgentCount int    `json:"agent_count,omitempty"`
}

// ListNamespacesResponse is returned by GET /api/v1/auth/namespaces.
type ListNamespacesResponse struct {
	Namespaces []Namespace `json:"namespaces"`
}

// ListNamespaces fetches the namespaces owned by the authenticated user.
// Uses the /api/ prefix on the hosted admin surface.
func (c *Client) ListNamespaces(ctx context.Context) (*ListNamespacesResponse, error) {
	var out ListNamespacesResponse
	if err := c.Get(ctx, "/api/v1/auth/namespaces", &out); err != nil {
		return nil, err
	}
	return &out, nil
}
