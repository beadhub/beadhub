package aweb

import "context"

type PolicyInvariant struct {
	ID     string `json:"id"`
	Title  string `json:"title"`
	BodyMD string `json:"body_md"`
}

type PolicyRolePlaybook struct {
	Title      string `json:"title"`
	PlaybookMD string `json:"playbook_md"`
}

type PolicySelectedRole struct {
	Role       string `json:"role"`
	Title      string `json:"title"`
	PlaybookMD string `json:"playbook_md"`
}

type ActivePolicyResponse struct {
	PolicyID     string                        `json:"policy_id"`
	ProjectID    string                        `json:"project_id"`
	Version      int                           `json:"version"`
	UpdatedAt    string                        `json:"updated_at"`
	Invariants   []PolicyInvariant             `json:"invariants"`
	Roles        map[string]PolicyRolePlaybook `json:"roles"`
	SelectedRole *PolicySelectedRole           `json:"selected_role,omitempty"`
}

type ActivePolicyParams struct {
	Role         string
	OnlySelected bool
}

func (c *Client) ActivePolicy(ctx context.Context, params ActivePolicyParams) (*ActivePolicyResponse, error) {
	path := "/v1/policies/active"
	sep := "?"
	if params.Role != "" {
		path += sep + "role=" + urlQueryEscape(params.Role)
		sep = "&"
	}
	path += sep + "only_selected=" + boolString(params.OnlySelected)
	var out ActivePolicyResponse
	if err := c.Get(ctx, path, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
