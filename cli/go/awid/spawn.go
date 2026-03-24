package awid

import (
	"context"
	"fmt"
)

// SpawnInviteCreateRequest is sent to POST /api/v1/spawn/create-invite.
type SpawnInviteCreateRequest struct {
	AliasHint        string `json:"alias_hint,omitempty"`
	AccessMode       string `json:"access_mode,omitempty"`
	MaxUses          int    `json:"max_uses,omitempty"`
	ExpiresInSeconds int    `json:"expires_in_seconds,omitempty"`
}

// SpawnInviteCreateResponse is returned by POST /api/v1/spawn/create-invite.
type SpawnInviteCreateResponse struct {
	InviteID      string `json:"invite_id"`
	Token         string `json:"token"`
	TokenPrefix   string `json:"token_prefix"`
	AliasHint     string `json:"alias_hint,omitempty"`
	AccessMode    string `json:"access_mode"`
	MaxUses       int    `json:"max_uses"`
	ExpiresAt     string `json:"expires_at"`
	NamespaceSlug string `json:"namespace_slug,omitempty"`
	Namespace     string `json:"namespace"`
	ServerURL     string `json:"server_url"`
}

// SpawnInviteListItem is returned by GET /api/v1/spawn/invites.
type SpawnInviteListItem struct {
	InviteID    string `json:"invite_id"`
	TokenPrefix string `json:"token_prefix"`
	AliasHint   string `json:"alias_hint,omitempty"`
	AccessMode  string `json:"access_mode"`
	MaxUses     int    `json:"max_uses"`
	CurrentUses int    `json:"current_uses"`
	ExpiresAt   string `json:"expires_at"`
	RevokedAt   string `json:"revoked_at,omitempty"`
	CreatedAt   string `json:"created_at"`
}

// SpawnInviteListResponse is returned by GET /api/v1/spawn/invites.
type SpawnInviteListResponse struct {
	Invites []SpawnInviteListItem `json:"invites"`
}

// SpawnAcceptInviteRequest is sent to POST /api/v1/spawn/accept-invite.
type SpawnAcceptInviteRequest struct {
	Token               string  `json:"token"`
	Alias               *string `json:"alias,omitempty"`
	Name                *string `json:"name,omitempty"`
	AddressReachability string  `json:"address_reachability,omitempty"`
	HumanName           string  `json:"human_name,omitempty"`
	AgentType           string  `json:"agent_type,omitempty"`
	DID                 string  `json:"did,omitempty"`
	PublicKey           string  `json:"public_key,omitempty"`
	Custody             string  `json:"custody,omitempty"`
	Lifetime            string  `json:"lifetime,omitempty"`
}

// SpawnCreateInvite creates a spawn invite token in the current identity
// context.
func (c *Client) SpawnCreateInvite(ctx context.Context, req *SpawnInviteCreateRequest) (*SpawnInviteCreateResponse, error) {
	if req == nil {
		req = &SpawnInviteCreateRequest{}
	}
	var out SpawnInviteCreateResponse
	if err := c.Post(ctx, "/api/v1/spawn/create-invite", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ListSpawnInvites returns the caller's active spawn invites.
func (c *Client) ListSpawnInvites(ctx context.Context) (*SpawnInviteListResponse, error) {
	var out SpawnInviteListResponse
	if err := c.Get(ctx, "/api/v1/spawn/invites", &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// RevokeSpawnInvite revokes a spawn invite by its invite_id.
func (c *Client) RevokeSpawnInvite(ctx context.Context, inviteID string) error {
	if inviteID == "" {
		return fmt.Errorf("aweb: invite_id is required")
	}
	return c.Delete(ctx, "/api/v1/spawn/invites/"+urlPathEscape(inviteID))
}

// SpawnAcceptInvite accepts a spawn invite token and bootstraps a new
// workspace identity.
func (c *Client) SpawnAcceptInvite(ctx context.Context, req *SpawnAcceptInviteRequest) (*BootstrapIdentityResponse, error) {
	if req == nil || req.Token == "" {
		return nil, fmt.Errorf("aweb: token is required")
	}
	var out BootstrapIdentityResponse
	if err := c.Post(ctx, "/api/v1/spawn/accept-invite", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
