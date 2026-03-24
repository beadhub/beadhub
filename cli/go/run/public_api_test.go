package run_test

import (
	"testing"

	awrun "github.com/awebai/aw/run"
)

type fakeUI struct{}

func (f *fakeUI) Start() error                      { return nil }
func (f *fakeUI) Stop() error                       { return nil }
func (f *fakeUI) Events() <-chan awrun.ControlEvent { return nil }
func (f *fakeUI) HasPendingInput() bool             { return false }
func (f *fakeUI) AppendText(string)                 {}
func (f *fakeUI) AppendLine(string)                 {}
func (f *fakeUI) SetInputLine(string)               {}
func (f *fakeUI) SetStatusLine(string)              {}
func (f *fakeUI) ClearStatusLine()                  {}
func (f *fakeUI) ClearInputLine()                   {}
func (f *fakeUI) SetExitConfirmation(bool)          {}
func (f *fakeUI) HasActiveProgram() bool            { return false }

func TestPublicUICanBeImplementedOutsideRunPackage(t *testing.T) {
	var control awrun.InputController = &fakeUI{}
	var ui awrun.UI = &fakeUI{}

	loop := awrun.Loop{Control: ui}
	if loop.Control != control {
		t.Fatal("expected public UI implementation to satisfy loop control")
	}
}
