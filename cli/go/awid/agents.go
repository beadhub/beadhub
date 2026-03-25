package awid

import "context"

// IdentityView is returned by GET /v1/agents.
type IdentityView struct {
	IdentityID          string `json:"identity_id,omitempty"`
	AgentID             string `json:"agent_id,omitempty"`
	Alias               string `json:"alias"`
	Name                string `json:"name,omitempty"`
	HumanName           string `json:"human_name,omitempty"`
	AgentType           string `json:"agent_type,omitempty"`
	Status              string `json:"status,omitempty"`
	LastSeen            string `json:"last_seen,omitempty"`
	Online              bool   `json:"online"`
	AccessMode          string `json:"access_mode,omitempty"`
	AddressReachability string `json:"address_reachability,omitempty"`
	NamespaceSlug       string `json:"namespace_slug,omitempty"`
	Lifetime            string `json:"lifetime,omitempty"`
}

func (v IdentityView) CurrentIdentityID() string {
	if v.IdentityID != "" {
		return v.IdentityID
	}
	return v.AgentID
}

type ListIdentitiesResponse struct {
	ProjectID  string         `json:"project_id"`
	Identities []IdentityView `json:"identities,omitempty"`
	Agents     []IdentityView `json:"agents,omitempty"`
}

func (c *Client) ListIdentities(ctx context.Context) (*ListIdentitiesResponse, error) {
	var out ListIdentitiesResponse
	if err := c.Get(ctx, "/v1/agents", &out); err != nil {
		return nil, err
	}
	if len(out.Identities) == 0 && len(out.Agents) != 0 {
		out.Identities = out.Agents
	}
	return &out, nil
}

type PatchIdentityRequest struct {
	AccessMode          string `json:"access_mode,omitempty"`
	AddressReachability string `json:"address_reachability,omitempty"`
}

type PatchIdentityResponse struct {
	IdentityID          string `json:"identity_id,omitempty"`
	AgentID             string `json:"agent_id,omitempty"`
	AccessMode          string `json:"access_mode,omitempty"`
	AddressReachability string `json:"address_reachability,omitempty"`
}

func (r PatchIdentityResponse) CurrentIdentityID() string {
	if r.IdentityID != "" {
		return r.IdentityID
	}
	return r.AgentID
}

func (c *Client) PatchIdentity(ctx context.Context, identityID string, req *PatchIdentityRequest) (*PatchIdentityResponse, error) {
	var out PatchIdentityResponse
	if err := c.Patch(ctx, "/v1/agents/"+urlPathEscape(identityID), req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// HeartbeatResponse is returned by POST /v1/agents/heartbeat.
type HeartbeatResponse struct {
	IdentityID string `json:"identity_id"`
	LastSeen   string `json:"last_seen"`
	TTL        int    `json:"ttl_seconds"`
}

// Heartbeat reports agent liveness to the aweb server.
func (c *Client) Heartbeat(ctx context.Context) (*HeartbeatResponse, error) {
	var out HeartbeatResponse
	if err := c.Post(ctx, "/v1/agents/heartbeat", nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
