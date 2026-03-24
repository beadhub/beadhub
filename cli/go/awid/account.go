package awid

// Account holds the persisted protocol identity fields for a selected identity.
// Coordination-layer extensions (e.g. DefaultProject) are added by
// the awconfig package via embedding.
type Account struct {
	Server         string `yaml:"server,omitempty"`
	APIKey         string `yaml:"api_key,omitempty"`
	IdentityID     string `yaml:"identity_id,omitempty"`
	IdentityHandle string `yaml:"identity_handle,omitempty"`
	Email          string `yaml:"email,omitempty"`
	NamespaceSlug  string `yaml:"namespace_slug,omitempty"`
	DID            string `yaml:"did,omitempty"`
	StableID       string `yaml:"stable_id,omitempty"`
	SigningKey     string `yaml:"signing_key,omitempty"`
	Custody        string `yaml:"custody,omitempty"`
	Lifetime       string `yaml:"lifetime,omitempty"`
}
