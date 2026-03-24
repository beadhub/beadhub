package awid

import (
	"context"
	"fmt"
	"strings"
)

type ControlSignal string

const (
	ControlSignalPause     ControlSignal = "pause"
	ControlSignalResume    ControlSignal = "resume"
	ControlSignalInterrupt ControlSignal = "interrupt"
)

type SendControlSignalRequest struct {
	Signal ControlSignal `json:"signal"`
}

type SendControlSignalResponse struct {
	SignalID string        `json:"signal_id"`
	Signal   ControlSignal `json:"signal"`
}

func (s ControlSignal) Valid() bool {
	switch s {
	case ControlSignalPause, ControlSignalResume, ControlSignalInterrupt:
		return true
	default:
		return false
	}
}

func (c *Client) SendControlSignal(ctx context.Context, alias string, signal ControlSignal) (*SendControlSignalResponse, error) {
	alias = strings.TrimSpace(alias)
	if alias == "" {
		return nil, fmt.Errorf("aweb: alias must not be empty")
	}
	if !signal.Valid() {
		return nil, fmt.Errorf("aweb: invalid control signal %q", signal)
	}

	req := &SendControlSignalRequest{Signal: signal}
	var out SendControlSignalResponse
	if err := c.Post(ctx, "/v1/agents/"+urlPathEscape(alias)+"/control", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) PauseAgent(ctx context.Context, alias string) (*SendControlSignalResponse, error) {
	return c.SendControlSignal(ctx, alias, ControlSignalPause)
}

func (c *Client) ResumeAgent(ctx context.Context, alias string) (*SendControlSignalResponse, error) {
	return c.SendControlSignal(ctx, alias, ControlSignalResume)
}

func (c *Client) InterruptAgent(ctx context.Context, alias string) (*SendControlSignalResponse, error) {
	return c.SendControlSignal(ctx, alias, ControlSignalInterrupt)
}
