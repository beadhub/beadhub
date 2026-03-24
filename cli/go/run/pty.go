package run

import (
	"context"
	"os/exec"

	"github.com/creack/pty"
)

func realPTYCommandRunner(ctx context.Context, dir string, argv []string, onLine func(string), sinks *commandOutputSinks) error {
	cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
	cmd.Dir = dir

	ptmx, err := pty.Start(cmd)
	if err != nil {
		return err
	}
	defer func() { _ = ptmx.Close() }()

	if sinks != nil && sinks.stdinReady != nil {
		sinks.stdinReady(ptmx)
	}

	if result := scanCommandPipe(ptmx, onLine, ptyPartialCallback(sinks), false, true, true); result.Err != nil {
		_ = cmd.Wait()
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return result.Err
	}

	if err := cmd.Wait(); err != nil {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return err
	}
	return nil
}

func ptyPartialCallback(sinks *commandOutputSinks) func(string) {
	if sinks == nil {
		return nil
	}
	return sinks.ptyPartial
}
