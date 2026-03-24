package run

import (
	"context"
	"time"

	awid "github.com/awebai/aw/awid"
)

// EventStreamOpener opens a single SSE connection. The EventBus calls this
// repeatedly with backoff to maintain a persistent stream.
type EventStreamOpener func(ctx context.Context, deadline time.Time) (awid.EventSource, error)

// NewEventStreamOpener returns an opener that connects to the given client's
// event stream endpoint.
func NewEventStreamOpener(client *awid.Client) EventStreamOpener {
	return func(ctx context.Context, deadline time.Time) (awid.EventSource, error) {
		return client.EventStream(ctx, deadline)
	}
}

func nextRetryDelay(delay, maxDelay time.Duration) time.Duration {
	next := delay * 2
	if next <= 0 {
		return maxDelay
	}
	if next > maxDelay {
		return maxDelay
	}
	return next
}

func sleepForRetry(ctx context.Context, nowFn func() time.Time, deadline time.Time, delay time.Duration) bool {
	if !deadline.IsZero() {
		remaining := deadline.Sub(nowFn())
		if remaining <= 0 {
			return false
		}
		if delay > remaining {
			delay = remaining
		}
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
