package awid

import "context"

type ContactCreateRequest struct {
	ContactAddress string `json:"contact_address"`
	Label          string `json:"label,omitempty"`
}

type ContactCreateResponse struct {
	ContactID      string `json:"contact_id"`
	ContactAddress string `json:"contact_address"`
	Label          string `json:"label"`
	CreatedAt      string `json:"created_at"`
}

type Contact struct {
	ContactID      string `json:"contact_id"`
	ContactAddress string `json:"contact_address"`
	Label          string `json:"label,omitempty"`
	CreatedAt      string `json:"created_at"`
}

type ContactListResponse struct {
	Contacts []Contact `json:"contacts"`
}

type ContactDeleteResponse struct {
	Deleted bool `json:"deleted"`
}

func (c *Client) CreateContact(ctx context.Context, req *ContactCreateRequest) (*ContactCreateResponse, error) {
	var out ContactCreateResponse
	if err := c.Post(ctx, "/v1/contacts", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ListContacts(ctx context.Context) (*ContactListResponse, error) {
	var out ContactListResponse
	if err := c.Get(ctx, "/v1/contacts", &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// DeleteContact removes a contact by ID. Uses do() directly because the
// existing delete() helper discards the response body.
func (c *Client) DeleteContact(ctx context.Context, contactID string) (*ContactDeleteResponse, error) {
	var out ContactDeleteResponse
	if err := c.Do(ctx, "DELETE", "/v1/contacts/"+urlPathEscape(contactID), nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
