package run

import (
	"context"
	"fmt"
	"os/exec"
	"strings"
	"sync"
	"time"
)

type ServiceManager struct {
	Logf         func(string)
	StartProcess ServiceStartFunc
	RestartDelay time.Duration
	cancel       context.CancelFunc
	wg           sync.WaitGroup
}

type ServiceStartFunc func(ctx context.Context, dir string, service ServiceConfig) (ServiceProcess, error)

type ServiceProcess interface {
	Wait() error
}

type execServiceProcess struct {
	cmd  *exec.Cmd
	done chan struct{}
}

func NewServiceManager(logf func(string)) *ServiceManager {
	manager := &ServiceManager{
		Logf:         logf,
		RestartDelay: time.Second,
	}
	manager.StartProcess = manager.startProcess
	return manager
}

func (m *ServiceManager) Start(ctx context.Context, services []ServiceConfig, dir string) error {
	if len(services) == 0 {
		return nil
	}
	if m.StartProcess == nil {
		m.StartProcess = m.startProcess
	}
	if m.RestartDelay <= 0 {
		m.RestartDelay = time.Second
	}
	if m.Logf == nil {
		m.Logf = func(string) {}
	}

	serviceCtx, cancel := context.WithCancel(ctx)
	m.cancel = cancel

	for _, service := range services {
		service := service
		m.wg.Add(1)
		go func() {
			defer m.wg.Done()
			m.supervise(serviceCtx, dir, service)
		}()
	}
	return nil
}

func (m *ServiceManager) Stop() error {
	if m.cancel != nil {
		m.cancel()
	}
	m.wg.Wait()
	return nil
}

func (m *ServiceManager) supervise(ctx context.Context, dir string, service ServiceConfig) {
	startedOnce := false
	for ctx.Err() == nil {
		process, err := m.StartProcess(ctx, dir, service)
		if err != nil {
			m.log(fmt.Sprintf("info: service %s failed to start: %v", service.Name, err))
			if !sleepService(ctx, m.RestartDelay) {
				return
			}
			continue
		}

		if startedOnce {
			m.log(fmt.Sprintf("info: service %s restarted", service.Name))
		} else {
			m.log(fmt.Sprintf("info: service %s started", service.Name))
			startedOnce = true
		}

		err = process.Wait()
		if ctx.Err() != nil {
			return
		}
		if err != nil {
			m.log(fmt.Sprintf("info: service %s exited: %v; restarting", service.Name, err))
		} else {
			m.log(fmt.Sprintf("info: service %s exited; restarting", service.Name))
		}
		if !sleepService(ctx, m.RestartDelay) {
			return
		}
	}
}

func (m *ServiceManager) log(line string) {
	if m.Logf != nil {
		m.Logf(line)
	}
}

func sleepService(ctx context.Context, d time.Duration) bool {
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}

func (m *ServiceManager) startProcess(ctx context.Context, dir string, service ServiceConfig) (ServiceProcess, error) {
	return StartServiceProcess(ctx, dir, service)
}

func StartServiceProcess(ctx context.Context, dir string, service ServiceConfig) (ServiceProcess, error) {
	cmd := exec.Command(defaultServiceShell(), "-lc", service.Command)
	cmd.Dir = dir
	setServiceProcessGroup(cmd)
	if err := cmd.Start(); err != nil {
		return nil, err
	}

	done := make(chan struct{})
	go watchServiceContext(ctx, cmd, done)

	return &execServiceProcess{cmd: cmd, done: done}, nil
}

func (p *execServiceProcess) Wait() error {
	err := p.cmd.Wait()
	close(p.done)
	return err
}

func watchServiceContext(ctx context.Context, cmd *exec.Cmd, done <-chan struct{}) {
	select {
	case <-ctx.Done():
		stopServiceCommand(cmd)
	case <-done:
	}
}

func stopServiceCommand(cmd *exec.Cmd) {
	killServiceProcessGroup(cmd)
}

func defaultServiceShell() string {
	return "/bin/sh"
}

func FormatServicesPromptSection(services []ServiceConfig) string {
	lines := make([]string, 0, len(services)+1)
	for _, service := range services {
		name := strings.TrimSpace(service.Name)
		if name == "" {
			continue
		}
		description := strings.TrimSpace(service.Description)
		if description == "" {
			description = strings.TrimSpace(service.Command)
		}
		if description == "" {
			continue
		}
		lines = append(lines, fmt.Sprintf("- %s: %s", name, description))
	}
	if len(lines) == 0 {
		return ""
	}
	return "Services available:\n" + strings.Join(lines, "\n")
}
