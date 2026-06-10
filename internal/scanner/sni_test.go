package scanner

import (
	"crypto/tls"
	"crypto/x509"
	"testing"
)

func TestCertMatchesDomainTrue(t *testing.T) {
	cert := &x509.Certificate{DNSNames: []string{"workers.dev"}}
	state := tls.ConnectionState{PeerCertificates: []*x509.Certificate{cert}}
	if !certMatchesDomain(state, "workers.dev") {
		t.Fatalf("expected certMatchesDomain to return true for workers.dev")
	}
}

func TestCertMatchesDomainFalse(t *testing.T) {
	cert := &x509.Certificate{DNSNames: []string{"example.com"}}
	state := tls.ConnectionState{PeerCertificates: []*x509.Certificate{cert}}
	if certMatchesDomain(state, "workers.dev") {
		t.Fatalf("expected certMatchesDomain to return false for mismatch")
	}
}

func TestLooksLikeHTMLResponse(t *testing.T) {
	if !looksLikeHTMLResponse([]byte("<!doctype html><html><body>Hello</body></html>")) {
		t.Fatalf("expected HTML detection to succeed")
	}
	if looksLikeHTMLResponse([]byte("{\"host\": \"workers.dev\"}")) {
		t.Fatalf("expected JSON not to be detected as HTML")
	}
}

func TestNewScannerDefaults(t *testing.T) {
	s := NewScanner(nil)
	_ = s
	if !probeRequireHTMLForDomainTokens {
		t.Fatalf("expected probeRequireHTMLForDomainTokens to default true when config is nil")
	}
	if !probeAcceptOnCertMatch {
		t.Fatalf("expected probeAcceptOnCertMatch to default true when config is nil")
	}
}

func TestNewScannerRespectsConfigFlags(t *testing.T) {
	cfg := &ScannerConfig{
		ProbeRequireHTMLForDomainTokens: false,
		ProbeAcceptOnCertMatch:          false,
	}
	s := NewScanner(cfg)
	_ = s
	if probeRequireHTMLForDomainTokens {
		t.Fatalf("expected probeRequireHTMLForDomainTokens to follow config=false")
	}
	if probeAcceptOnCertMatch {
		t.Fatalf("expected probeAcceptOnCertMatch to follow config=false")
	}
}

func TestMinimumDomainAcceptScore(t *testing.T) {
	tests := []struct {
		domainCount int
		want        int
	}{
		{domainCount: 1, want: 1},
		{domainCount: 2, want: 2},
		{domainCount: 6, want: 2},
		{domainCount: 9, want: 1},
		{domainCount: 10, want: 1},
	}

	for _, tc := range tests {
		if got := minimumDomainAcceptScore(tc.domainCount); got != tc.want {
			t.Fatalf("minimumDomainAcceptScore(%d) = %d, want %d", tc.domainCount, got, tc.want)
		}
	}
}
