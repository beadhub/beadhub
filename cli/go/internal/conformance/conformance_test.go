package conformance_test

import (
	"crypto/ed25519"
	"embed"
	"encoding/hex"
	"encoding/json"
	"testing"

	awid "github.com/awebai/aw/awid"
)

//go:embed vectors/*.json
var vectorsFS embed.FS

// --- message-signing-v1 ---

type messageSigningVector struct {
	Name             string        `json:"name"`
	SigningSeedHex   string        `json:"signing_seed_hex"`
	SigningDIDKey    string        `json:"signing_did_key"`
	Message          messageFields `json:"message"`
	CanonicalPayload string        `json:"canonical_payload"`
	SignatureB64     string        `json:"signature_b64"`
}

type messageFields struct {
	From         string `json:"from"`
	FromDID      string `json:"from_did"`
	To           string `json:"to"`
	ToDID        string `json:"to_did"`
	Type         string `json:"type"`
	MessageID    string `json:"message_id"`
	Subject      string `json:"subject"`
	Body         string `json:"body"`
	Timestamp    string `json:"timestamp"`
	FromStableID string `json:"from_stable_id"`
	ToStableID   string `json:"to_stable_id"`
}

func TestMessageSigningVectors(t *testing.T) {
	data, err := vectorsFS.ReadFile("vectors/message-signing-v1.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors []messageSigningVector
	if err := json.Unmarshal(data, &vectors); err != nil {
		t.Fatal(err)
	}

	for _, v := range vectors {
		t.Run(v.Name, func(t *testing.T) {
			seed, err := hex.DecodeString(v.SigningSeedHex)
			if err != nil {
				t.Fatal(err)
			}
			key := ed25519.NewKeyFromSeed(seed)

			// Verify did:key matches seed.
			got := awid.ComputeDIDKey(key.Public().(ed25519.PublicKey))
			if got != v.SigningDIDKey {
				t.Fatalf("ComputeDIDKey: got %s, want %s", got, v.SigningDIDKey)
			}

			env := &awid.MessageEnvelope{
				From:         v.Message.From,
				FromDID:      v.Message.FromDID,
				To:           v.Message.To,
				ToDID:        v.Message.ToDID,
				Type:         v.Message.Type,
				MessageID:    v.Message.MessageID,
				Subject:      v.Message.Subject,
				Body:         v.Message.Body,
				Timestamp:    v.Message.Timestamp,
				FromStableID: v.Message.FromStableID,
				ToStableID:   v.Message.ToStableID,
			}

			// Test canonical payload matches expected.
			canonical := awid.CanonicalJSON(env)
			if canonical != v.CanonicalPayload {
				t.Errorf("CanonicalJSON:\n  got:  %s\n  want: %s", canonical, v.CanonicalPayload)
			}

			// Test signing produces expected signature.
			sig, err := awid.SignMessage(key, env)
			if err != nil {
				t.Fatal(err)
			}
			if sig != v.SignatureB64 {
				t.Errorf("SignMessage:\n  got:  %s\n  want: %s", sig, v.SignatureB64)
			}

			// Test verification succeeds.
			env.Signature = v.SignatureB64
			env.SigningKeyID = v.SigningDIDKey
			status, verifyErr := awid.VerifyMessage(env)
			if verifyErr != nil {
				t.Errorf("VerifyMessage error: %v", verifyErr)
			}
			if status != awid.Verified {
				t.Errorf("VerifyMessage: got %s, want %s", status, awid.Verified)
			}
		})
	}
}

// --- stable-id-v1 ---

type stableIDVector struct {
	Name         string `json:"name"`
	SeedHex      string `json:"seed_hex"`
	DIDKey       string `json:"did_key"`
	PublicKeyHex string `json:"public_key_hex"`
	StableIDAW   string `json:"stable_id_aw"`
}

func TestStableIDVectors(t *testing.T) {
	data, err := vectorsFS.ReadFile("vectors/stable-id-v1.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors []stableIDVector
	if err := json.Unmarshal(data, &vectors); err != nil {
		t.Fatal(err)
	}

	for _, v := range vectors {
		t.Run(v.Name, func(t *testing.T) {
			pub, err := awid.ExtractPublicKey(v.DIDKey)
			if err != nil {
				t.Fatal(err)
			}

			// Verify public key hex matches.
			if hex.EncodeToString(pub) != v.PublicKeyHex {
				t.Errorf("public key hex: got %s, want %s", hex.EncodeToString(pub), v.PublicKeyHex)
			}

			gotAW := awid.ComputeStableID(pub)
			if gotAW != v.StableIDAW {
				t.Errorf("ComputeStableID: got %s, want %s", gotAW, v.StableIDAW)
			}
		})
	}
}

// --- rotation-announcements-v1 ---

type rotationVector struct {
	Name               string         `json:"name"`
	Links              []rotationLink `json:"links"`
	PinnedDIDKey       string         `json:"pinned_did_key"`
	EnvelopeFromDIDKey string         `json:"envelope_from_did_key"`
}

type rotationLink struct {
	OldSeedHex       string `json:"old_seed_hex"`
	OldDIDKey        string `json:"old_did_key"`
	NewDIDKey        string `json:"new_did_key"`
	Timestamp        string `json:"timestamp"`
	CanonicalPayload string `json:"canonical_payload"`
	SignatureB64     string `json:"signature_b64"`
}

func TestRotationAnnouncementVectors(t *testing.T) {
	data, err := vectorsFS.ReadFile("vectors/rotation-announcements-v1.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors []rotationVector
	if err := json.Unmarshal(data, &vectors); err != nil {
		t.Fatal(err)
	}

	for _, v := range vectors {
		t.Run(v.Name, func(t *testing.T) {
			for i, link := range v.Links {
				oldPub, err := awid.ExtractPublicKey(link.OldDIDKey)
				if err != nil {
					t.Fatalf("link %d: ExtractPublicKey: %v", i, err)
				}

				// Verify canonical payload matches expected.
				gotCanonical := awid.CanonicalRotationJSON(link.OldDIDKey, link.NewDIDKey, link.Timestamp)
				if gotCanonical != link.CanonicalPayload {
					t.Errorf("link %d: CanonicalRotationJSON:\n  got:  %s\n  want: %s", i, gotCanonical, link.CanonicalPayload)
				}

				// Verify rotation signature.
				ok, err := awid.VerifyRotationSignature(oldPub, link.OldDIDKey, link.NewDIDKey, link.Timestamp, link.SignatureB64)
				if err != nil {
					t.Fatalf("link %d: VerifyRotationSignature: %v", i, err)
				}
				if !ok {
					t.Errorf("link %d: VerifyRotationSignature returned false", i)
				}

				// Verify signing with the old key produces the expected signature.
				seed, err := hex.DecodeString(link.OldSeedHex)
				if err != nil {
					t.Fatal(err)
				}
				key := ed25519.NewKeyFromSeed(seed)
				sig, err := awid.SignRotation(key, link.OldDIDKey, link.NewDIDKey, link.Timestamp)
				if err != nil {
					t.Fatalf("link %d: SignRotation: %v", i, err)
				}
				if sig != link.SignatureB64 {
					t.Errorf("link %d: SignRotation:\n  got:  %s\n  want: %s", i, sig, link.SignatureB64)
				}
			}

			// Verify chain semantics: first link's old_did matches pinned,
			// each link's new_did matches next link's old_did,
			// last link's new_did matches envelope from_did.
			if len(v.Links) > 0 {
				if v.Links[0].OldDIDKey != v.PinnedDIDKey {
					t.Errorf("chain: first link old_did %s != pinned %s", v.Links[0].OldDIDKey, v.PinnedDIDKey)
				}
				for i := 1; i < len(v.Links); i++ {
					if v.Links[i].OldDIDKey != v.Links[i-1].NewDIDKey {
						t.Errorf("chain: link %d old_did %s != link %d new_did %s", i, v.Links[i].OldDIDKey, i-1, v.Links[i-1].NewDIDKey)
					}
				}
				lastNew := v.Links[len(v.Links)-1].NewDIDKey
				if lastNew != v.EnvelopeFromDIDKey {
					t.Errorf("chain: last new_did %s != envelope from_did %s", lastNew, v.EnvelopeFromDIDKey)
				}
			}
		})
	}
}

func strField(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func intField(m map[string]interface{}, key string) int {
	if v, ok := m[key].(float64); ok {
		return int(v)
	}
	return 0
}
