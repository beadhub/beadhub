package main

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestAwLockMutationUnsupportedMessage(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		args       []string
		path       string
		statusCode int
	}{
		{name: "acquire", args: []string{"lock", "acquire", "--resource-key", "deploy"}, path: "/v1/reservations", statusCode: http.StatusMethodNotAllowed},
		{name: "renew", args: []string{"lock", "renew", "--resource-key", "deploy"}, path: "/v1/reservations/renew", statusCode: http.StatusNotFound},
		{name: "release", args: []string{"lock", "release", "--resource-key", "deploy"}, path: "/v1/reservations/release", statusCode: http.StatusNotFound},
		{name: "revoke", args: []string{"lock", "revoke", "--prefix", "deploy"}, path: "/v1/reservations/revoke", statusCode: http.StatusNotFound},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			server := newLocalHTTPServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch r.URL.Path {
				case tc.path:
					w.WriteHeader(tc.statusCode)
					_ = json.NewEncoder(w).Encode(map[string]any{"detail": "unsupported"})
				case "/v1/agents/heartbeat":
					w.WriteHeader(http.StatusOK)
				default:
					t.Fatalf("unexpected %s %s", r.Method, r.URL.Path)
				}
			}))

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()

			tmp := t.TempDir()
			bin := filepath.Join(tmp, "aw")
			cfgPath := filepath.Join(tmp, "config.yaml")
			buildAwBinary(t, ctx, bin)

			if err := os.WriteFile(cfgPath, []byte(strings.TrimSpace(`
servers:
  local:
    url: `+server.URL+`
accounts:
  acct:
    server: local
    api_key: aw_sk_test
default_account: acct
`)+"\n"), 0o600); err != nil {
				t.Fatalf("write config: %v", err)
			}

			run := exec.CommandContext(ctx, bin, tc.args...)
			run.Env = append(os.Environ(), "AW_CONFIG_PATH="+cfgPath, "AWEB_URL=", "AWEB_API_KEY=")
			run.Dir = tmp
			out, err := run.CombinedOutput()
			if err == nil {
				t.Fatalf("expected error, got success:\n%s", string(out))
			}
			if !strings.Contains(string(out), "only `aw lock list` is currently available") {
				t.Fatalf("unexpected output:\n%s", string(out))
			}
		})
	}
}
