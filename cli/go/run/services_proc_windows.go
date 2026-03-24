//go:build windows

package run

import (
	"os/exec"
)

func setServiceProcessGroup(cmd *exec.Cmd) {}

func killServiceProcessGroup(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	_ = cmd.Process.Kill()
}
