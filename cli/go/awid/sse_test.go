package awid

import (
	"io"
	"strings"
	"testing"
)

func TestSSEStreamParsesIDAndRetry(t *testing.T) {
	t.Parallel()

	stream := NewSSEStream(io.NopCloser(strings.NewReader(
		"id: 42\n" +
			"retry: 1500\n" +
			"event: actionable_chat\n" +
			"data: {\"message_id\":\"m1\"}\n" +
			"\n",
	)))

	ev, err := stream.Next()
	if err != nil {
		t.Fatalf("Next returned error: %v", err)
	}
	if ev.ID != "42" {
		t.Fatalf("id=%q", ev.ID)
	}
	if ev.Retry != 1500 {
		t.Fatalf("retry=%d", ev.Retry)
	}
	if ev.Event != "actionable_chat" {
		t.Fatalf("event=%q", ev.Event)
	}
	if ev.Data != "{\"message_id\":\"m1\"}" {
		t.Fatalf("data=%q", ev.Data)
	}
}

func TestSSEStreamPreservesDataSpacingPerSpec(t *testing.T) {
	t.Parallel()

	stream := NewSSEStream(io.NopCloser(strings.NewReader(
		"data:  padded\n" +
			"data:\n" +
			"data:tail\n" +
			"\n",
	)))

	ev, err := stream.Next()
	if err != nil {
		t.Fatalf("Next returned error: %v", err)
	}
	if ev.Data != " padded\n\ntail" {
		t.Fatalf("data=%q", ev.Data)
	}
}

func TestSSEStreamIgnoresInvalidRetry(t *testing.T) {
	t.Parallel()

	stream := NewSSEStream(io.NopCloser(strings.NewReader(
		"retry: nope\n" +
			"event: ping\n" +
			"data: ok\n\n",
	)))

	ev, err := stream.Next()
	if err != nil {
		t.Fatalf("Next returned error: %v", err)
	}
	if ev.Retry != -1 {
		t.Fatalf("retry=%d", ev.Retry)
	}
}
