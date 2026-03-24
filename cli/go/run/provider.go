package run

import (
	"encoding/json"
	"fmt"
	"strings"
)

func NewProvider(name string) (Provider, error) {
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "", "claude":
		return ClaudeProvider{}, nil
	case "codex":
		return CodexProvider{}, nil
	default:
		return nil, fmt.Errorf("unsupported provider %q", name)
	}
}

type ClaudeProvider struct{}

type ClaudeEnvelope struct {
	Type       string          `json:"type"`
	Subtype    string          `json:"subtype"`
	Event      ClaudeEvent     `json:"event"`
	Message    json.RawMessage `json:"message"`
	Content    any             `json:"content"`
	DurationMS int             `json:"duration_ms"`
	Stats      struct {
		DurationMS int `json:"duration_ms"`
	} `json:"stats"`
	CostUSD      *float64 `json:"cost_usd"`
	TotalCostUSD *float64 `json:"total_cost_usd"`
	Session      string   `json:"session_id"`
	CWD          string   `json:"cwd"`
	Model        string   `json:"model"`
	Result       string   `json:"result"`
	IsError      bool     `json:"is_error"`
}

type ClaudeEvent struct {
	Delta struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"delta"`
}
