package awid

import (
	"context"
	"fmt"
)

// ClaimHumanRequest is sent to POST /api/v1/claim-human.
// Attaches a human principal to the existing org, enabling
// dashboard access and team management.
type ClaimHumanRequest struct {
	Email string `json:"email"`
}

// ClaimHumanResponse is returned by POST /api/v1/claim-human.
type ClaimHumanResponse struct {
	Status      string `json:"status"`
	Message     string `json:"message"`
	Email       string `json:"email,omitempty"`
	OrgID       string `json:"org_id,omitempty"`
	OrgSlug     string `json:"org_slug,omitempty"`
	ProjectID   string `json:"project_id,omitempty"`
	ProjectSlug string `json:"project_slug,omitempty"`
}

// ClaimHuman initiates a human account claim for the current agent's org.
func (c *Client) ClaimHuman(ctx context.Context, req *ClaimHumanRequest) (*ClaimHumanResponse, error) {
	if req.Email == "" {
		return nil, fmt.Errorf("aweb: email is required for claim-human")
	}
	var out ClaimHumanResponse
	if err := c.Post(ctx, "/api/v1/claim-human", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
