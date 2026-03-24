package awid

import (
	"context"
	"fmt"
	"strings"
)

// AgentLogEntry is a single entry in an agent's identity log.
type AgentLogEntry struct {
	Operation string `json:"operation"`
	DID       string `json:"did,omitempty"`
	OldDID    string `json:"old_did,omitempty"`
	NewDID    string `json:"new_did,omitempty"`
	Timestamp string `json:"timestamp"`
	SignedBy  string `json:"signed_by"`
}

// AgentLogResponse is returned by GET /v1/agents/me/log or /v1/agents/{ns}/{alias}/log.
type AgentLogResponse struct {
	Entries []AgentLogEntry `json:"entries"`
}

// AgentLog fetches the identity log for an agent.
// If address is empty, fetches the caller's own log (requires API key).
// Otherwise address should be "namespace/alias" for a peer lookup.
func (c *Client) AgentLog(ctx context.Context, address string) (*AgentLogResponse, error) {
	var path string
	if address == "" {
		path = "/v1/agents/me/log"
	} else {
		parts := strings.SplitN(address, "/", 2)
		if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
			return nil, fmt.Errorf("address must be namespace/alias, got %q", address)
		}
		path = "/v1/agents/" + urlPathEscape(parts[0]) + "/" + urlPathEscape(parts[1]) + "/log"
	}
	var out AgentLogResponse
	if err := c.Get(ctx, path, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
