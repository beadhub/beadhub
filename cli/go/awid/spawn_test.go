package awid

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSpawnInviteCreate(t *testing.T) {
	t.Parallel()

	var gotAuth string
	var gotBody map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method=%s", r.Method)
		}
		if r.URL.Path != "/api/v1/spawn/create-invite" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		gotAuth = r.Header.Get("Authorization")
		if err := json.NewDecoder(r.Body).Decode(&gotBody); err != nil {
			t.Fatal(err)
		}
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"invite_id":      "inv-1",
			"token":          "aw_inv_test",
			"token_prefix":   "test1234",
			"alias_hint":     "reviewer",
			"access_mode":    "owner_only",
			"max_uses":       5,
			"expires_at":     "2026-03-27T18:00:00Z",
			"namespace_slug": "myteam",
			"namespace":      "myteam.aweb.ai",
			"server_url":     "https://app.aweb.ai/api",
		})
	}))
	t.Cleanup(server.Close)

	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}

	resp, err := c.SpawnCreateInvite(context.Background(), &SpawnInviteCreateRequest{
		AliasHint:        "reviewer",
		AccessMode:       "owner_only",
		MaxUses:          5,
		ExpiresInSeconds: 7 * 24 * 60 * 60,
	})
	if err != nil {
		t.Fatal(err)
	}

	if gotAuth != "Bearer aw_sk_test" {
		t.Fatalf("auth=%q", gotAuth)
	}
	if gotBody["alias_hint"] != "reviewer" {
		t.Fatalf("alias_hint=%v", gotBody["alias_hint"])
	}
	if gotBody["access_mode"] != "owner_only" {
		t.Fatalf("access_mode=%v", gotBody["access_mode"])
	}
	if gotBody["max_uses"] != float64(5) {
		t.Fatalf("max_uses=%v", gotBody["max_uses"])
	}
	if gotBody["expires_in_seconds"] != float64(604800) {
		t.Fatalf("expires_in_seconds=%v", gotBody["expires_in_seconds"])
	}
	if resp.Token != "aw_inv_test" {
		t.Fatalf("token=%q", resp.Token)
	}
	if resp.ServerURL != "https://app.aweb.ai/api" {
		t.Fatalf("server_url=%q", resp.ServerURL)
	}
}

func TestSpawnInviteListAndRevoke(t *testing.T) {
	t.Parallel()

	var gotDeletePath string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v1/spawn/invites":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"invites": []map[string]any{
					{
						"invite_id":    "inv-1",
						"token_prefix": "7f3k9x2m",
						"alias_hint":   "reviewer",
						"access_mode":  "contacts_only",
						"max_uses":     5,
						"current_uses": 2,
						"expires_at":   "2026-03-27T18:00:00Z",
						"created_at":   "2026-03-20T18:00:00Z",
					},
				},
			})
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v1/spawn/invites/inv-1":
			gotDeletePath = r.URL.Path
			w.WriteHeader(http.StatusNoContent)
		default:
			t.Fatalf("method=%s path=%s", r.Method, r.URL.Path)
		}
	}))
	t.Cleanup(server.Close)

	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}

	list, err := c.ListSpawnInvites(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(list.Invites) != 1 {
		t.Fatalf("len(invites)=%d", len(list.Invites))
	}
	if list.Invites[0].TokenPrefix != "7f3k9x2m" {
		t.Fatalf("token_prefix=%q", list.Invites[0].TokenPrefix)
	}

	if err := c.RevokeSpawnInvite(context.Background(), "inv-1"); err != nil {
		t.Fatal(err)
	}
	if gotDeletePath != "/api/v1/spawn/invites/inv-1" {
		t.Fatalf("delete path=%q", gotDeletePath)
	}
}

func TestSpawnAcceptInvite(t *testing.T) {
	t.Parallel()

	var gotAuth string
	var gotBody map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method=%s", r.Method)
		}
		if r.URL.Path != "/api/v1/spawn/accept-invite" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		gotAuth = r.Header.Get("Authorization")
		if err := json.NewDecoder(r.Body).Decode(&gotBody); err != nil {
			t.Fatal(err)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"project_id":     "proj-1",
			"project_slug":   "myteam",
			"namespace_slug": "myteam",
			"namespace":      "myteam.aweb.ai",
			"identity_id":    "identity-1",
			"alias":          "reviewer",
			"address":        "myteam.aweb.ai/reviewer",
			"api_key":        "aw_sk_invited",
			"server_url":     "https://app.aweb.ai/api",
			"did":            "did:key:z6MkInvite",
			"stable_id":      "did:aw:invite",
			"custody":        "self",
			"lifetime":       "persistent",
			"access_mode":    "owner_only",
			"created":        true,
		})
	}))
	t.Cleanup(server.Close)

	c, err := New(server.URL)
	if err != nil {
		t.Fatal(err)
	}

	resp, err := c.SpawnAcceptInvite(context.Background(), &SpawnAcceptInviteRequest{
		Token:     "aw_inv_test",
		HumanName: "Alice",
		AgentType: "agent",
		DID:       "did:key:z6MkLocal",
		PublicKey: "base64key",
		Custody:   CustodySelf,
		Lifetime:  LifetimePersistent,
	})
	if err != nil {
		t.Fatal(err)
	}

	if gotAuth != "" {
		t.Fatalf("auth=%q", gotAuth)
	}
	if _, ok := gotBody["alias"]; ok {
		t.Fatalf("alias should be omitted when not provided: %+v", gotBody)
	}
	if gotBody["token"] != "aw_inv_test" {
		t.Fatalf("token=%v", gotBody["token"])
	}
	if resp.Alias != "reviewer" {
		t.Fatalf("alias=%q", resp.Alias)
	}
	if resp.IdentityID != "identity-1" {
		t.Fatalf("identity_id=%q", resp.IdentityID)
	}
}
