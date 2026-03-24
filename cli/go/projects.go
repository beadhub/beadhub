package aweb

import "context"

// ProjectResponse is returned by GET /v1/projects/current.
type ProjectResponse struct {
	ProjectID string `json:"project_id"`
	Slug      string `json:"slug"`
	Name      string `json:"name"`
}

// GetCurrentProject returns the project associated with the current auth context.
func (c *Client) GetCurrentProject(ctx context.Context) (*ProjectResponse, error) {
	var out ProjectResponse
	if err := c.Get(ctx, "/v1/projects/current", &out); err != nil {
		return nil, err
	}
	return &out, nil
}
