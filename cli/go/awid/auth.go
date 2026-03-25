package awid

import "context"

// IntrospectResponse is returned by GET /v1/auth/introspect.
type IntrospectResponse struct {
	ProjectID     string `json:"project_id"`
	APIKeyID      string `json:"api_key_id,omitempty"`
	IdentityID    string `json:"identity_id,omitempty"`
	AgentID       string `json:"agent_id,omitempty"`
	Alias         string `json:"alias,omitempty"`
	Name          string `json:"name,omitempty"`
	HumanName     string `json:"human_name,omitempty"`
	AgentType     string `json:"agent_type,omitempty"`
	AccessMode    string `json:"access_mode,omitempty"`
	UserID        string `json:"user_id,omitempty"`
	NamespaceSlug string `json:"namespace_slug,omitempty"`
	Address       string `json:"address,omitempty"`
}

func (r *IntrospectResponse) IdentityHandle() string {
	if r == nil {
		return ""
	}
	if r.Name != "" {
		return r.Name
	}
	return r.Alias
}

func (r *IntrospectResponse) CurrentIdentityID() string {
	if r == nil {
		return ""
	}
	if r.IdentityID != "" {
		return r.IdentityID
	}
	return r.AgentID
}

// Introspect validates the client's Bearer token and returns the scoped project_id.
func (c *Client) Introspect(ctx context.Context) (*IntrospectResponse, error) {
	var out IntrospectResponse
	if err := c.Get(ctx, "/v1/auth/introspect", &out); err != nil {
		return nil, err
	}
	return &out, nil
}
