package awid

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestClaimHuman(t *testing.T) {
	t.Parallel()

	var gotBody map[string]any
	var gotAuth string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/claim-human" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Fatalf("method=%s", r.Method)
		}
		gotAuth = r.Header.Get("Authorization")
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status":       "verification_sent",
			"message":      "Check your inbox for a verification email",
			"email":        "alice@example.com",
			"org_id":       "org-1",
			"org_slug":     "myteam",
			"project_id":   "proj-1",
			"project_slug": "default",
		})
	}))
	t.Cleanup(server.Close)

	// Authenticated client — claim-human requires an agent key.
	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}

	resp, err := c.ClaimHuman(context.Background(), &ClaimHumanRequest{
		Email: "alice@example.com",
	})
	if err != nil {
		t.Fatal(err)
	}

	// Verify auth header.
	if gotAuth != "Bearer aw_sk_test" {
		t.Fatalf("auth=%q", gotAuth)
	}

	// Verify request body.
	if gotBody["email"] != "alice@example.com" {
		t.Fatalf("request email=%v", gotBody["email"])
	}

	// Verify response.
	if resp.Status != "verification_sent" {
		t.Fatalf("status=%q", resp.Status)
	}
	if resp.Message != "Check your inbox for a verification email" {
		t.Fatalf("message=%q", resp.Message)
	}
	if resp.Email != "alice@example.com" {
		t.Fatalf("email=%q", resp.Email)
	}
	if resp.OrgSlug != "myteam" {
		t.Fatalf("org_slug=%q", resp.OrgSlug)
	}
	if resp.ProjectSlug != "default" {
		t.Fatalf("project_slug=%q", resp.ProjectSlug)
	}
}

func TestClaimHumanHTTPError(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error":"not authorized"}`))
	}))
	t.Cleanup(server.Close)

	c, err := NewWithAPIKey(server.URL, "aw_sk_test")
	if err != nil {
		t.Fatal(err)
	}

	_, err = c.ClaimHuman(context.Background(), &ClaimHumanRequest{
		Email: "alice@example.com",
	})
	if err == nil {
		t.Fatal("expected error")
	}
	code, ok := HTTPStatusCode(err)
	if !ok || code != 403 {
		t.Fatalf("expected 403, got %d (ok=%v)", code, ok)
	}
}
