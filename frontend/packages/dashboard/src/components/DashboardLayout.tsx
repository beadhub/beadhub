import { useState } from 'react'
import { Menu } from 'lucide-react'
import { DashboardMobileDrawer } from './DashboardMobileDrawer'
import { DashboardSidebar } from './DashboardSidebar'
import { FilterBar } from './FilterBar'
import { navItems } from './nav-items'
import type { DashboardLayoutProps } from './types'

export function DashboardLayout({
  children,
  topBar,
  sidebar,
  sidebarProps = {},
  filterBarProps = {}
}: DashboardLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // When topBar is provided, hide the sidebar logo to avoid duplication
  const hasTopBar = Boolean(topBar)

  // Desktop sidebar (no close button)
  const desktopSidebar = sidebar ?? (
    <DashboardSidebar
      items={navItems}
      hideLogo={hasTopBar}
      {...sidebarProps}
    />
  )

  // Mobile sidebar (with close button)
  const mobileSidebar = sidebar ?? (
    <DashboardSidebar
      items={navItems}
      onNavClick={() => setSidebarOpen(false)}
      showCloseButton
      hideLogo={hasTopBar}
      {...sidebarProps}
    />
  )

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Top Bar (embedded-specific, optional) */}
      {topBar && (
        <header className="sticky top-0 z-40 border-b bg-background">
          {topBar}
        </header>
      )}

      <div className="flex flex-1">
        {/* Sidebar - Desktop */}
        <aside className="hidden md:flex md:w-56 md:flex-col md:fixed md:inset-y-0 border-r bg-background"
          style={topBar ? { top: 'var(--topbar-height, 56px)' } : undefined}
        >
          {desktopSidebar}
        </aside>

        {/* Mobile Drawer */}
        <DashboardMobileDrawer
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          topContent={topBar}
        >
          {mobileSidebar}
        </DashboardMobileDrawer>

        {/* Main Content */}
        <div className="flex-1 md:ml-56 flex flex-col">
          {/* Mobile Header - only show hamburger when topBar handles branding */}
          <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background/95 backdrop-blur px-4 md:hidden">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 -ml-2 hover:bg-secondary/50 rounded-md"
              aria-label="Open navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
            {!hasTopBar && <span className="font-semibold">BeadHub</span>}
          </header>

          {/* Filter Bar */}
          <div className="border-b bg-background">
            <div className="px-4">
              <FilterBar {...filterBarProps} />
            </div>
          </div>

          {/* Page Content */}
          <main className="flex-1 px-3 py-4 sm:px-4 sm:py-6 w-full max-w-6xl min-w-0">
            {children}
          </main>

          {/* Footer */}
          <footer className="border-t py-4">
            <div className="px-4 text-xs text-muted-foreground">
              <span className="opacity-60">BeadHub</span>
            </div>
          </footer>
        </div>
      </div>
    </div>
  )
}
