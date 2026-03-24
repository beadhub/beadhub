package aweb

import "context"

type CoordinationWorkspace struct {
	WorkspaceID    string `json:"workspace_id,omitempty"`
	ProjectID      string `json:"project_id,omitempty"`
	ProjectSlug    string `json:"project_slug,omitempty"`
	RepoID         string `json:"repo_id,omitempty"`
	WorkspaceCount int    `json:"workspace_count,omitempty"`
}

type CoordinationAgent struct {
	WorkspaceID     string  `json:"workspace_id"`
	Alias           string  `json:"alias"`
	Member          *string `json:"member,omitempty"`
	HumanName       *string `json:"human_name,omitempty"`
	Program         *string `json:"program,omitempty"`
	Role            *string `json:"role,omitempty"`
	Status          string  `json:"status"`
	CurrentBranch   *string `json:"current_branch,omitempty"`
	CanonicalOrigin *string `json:"canonical_origin,omitempty"`
	Timezone        *string `json:"timezone,omitempty"`
	CurrentIssue    *string `json:"current_issue,omitempty"`
	LastSeen        *string `json:"last_seen,omitempty"`
}

type CoordinationClaim struct {
	BeadID        string  `json:"bead_id"`
	WorkspaceID   string  `json:"workspace_id"`
	Alias         string  `json:"alias"`
	HumanName     *string `json:"human_name,omitempty"`
	ClaimedAt     string  `json:"claimed_at"`
	ClaimantCount int     `json:"claimant_count"`
	Title         *string `json:"title,omitempty"`
	ProjectID     string  `json:"project_id"`
}

type CoordinationConflictClaimant struct {
	Alias       string  `json:"alias"`
	HumanName   *string `json:"human_name,omitempty"`
	WorkspaceID string  `json:"workspace_id"`
}

type CoordinationConflict struct {
	BeadID    string                         `json:"bead_id"`
	Claimants []CoordinationConflictClaimant `json:"claimants"`
}

type CoordinationStatusResponse struct {
	Workspace          CoordinationWorkspace  `json:"workspace"`
	Agents             []CoordinationAgent    `json:"agents"`
	Claims             []CoordinationClaim    `json:"claims"`
	Conflicts          []CoordinationConflict `json:"conflicts"`
	EscalationsPending int                    `json:"escalations_pending"`
	Timestamp          string                 `json:"timestamp"`
}

func (c *Client) CoordinationStatus(ctx context.Context, workspaceID string) (*CoordinationStatusResponse, error) {
	path := "/v1/status"
	if workspaceID != "" {
		path += "?workspace_id=" + urlQueryEscape(workspaceID)
	}
	var out CoordinationStatusResponse
	if err := c.Get(ctx, path, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
