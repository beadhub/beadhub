package awid

import "strings"

// NetworkAddress represents either a network address (org-slug/alias)
// or a plain local alias.
type NetworkAddress struct {
	OrgSlug   string
	Alias     string
	IsNetwork bool
}

// ParseNetworkAddress parses a target string into a NetworkAddress.
// If the string contains a '/', it is treated as a network address (org-slug/alias).
// Otherwise it is a plain local alias.
func ParseNetworkAddress(target string) NetworkAddress {
	target = strings.TrimSpace(target)
	if target == "" {
		return NetworkAddress{}
	}

	idx := strings.IndexByte(target, '/')
	if idx < 0 {
		return NetworkAddress{Alias: target}
	}

	orgSlug := strings.TrimSpace(target[:idx])
	alias := strings.TrimSpace(target[idx+1:])
	if orgSlug == "" || alias == "" || strings.ContainsRune(alias, '/') {
		return NetworkAddress{}
	}

	return NetworkAddress{
		OrgSlug:   orgSlug,
		Alias:     alias,
		IsNetwork: true,
	}
}

// String returns the canonical string form of the address.
func (a NetworkAddress) String() string {
	if a.IsNetwork {
		return a.OrgSlug + "/" + a.Alias
	}
	return a.Alias
}
