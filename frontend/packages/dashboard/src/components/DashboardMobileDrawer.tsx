import type { DashboardMobileDrawerProps } from './types'

export function DashboardMobileDrawer({
  isOpen,
  onClose,
  topContent,
  children,
}: DashboardMobileDrawerProps) {
  return (
    <>
      {/* Overlay - always rendered, opacity controlled by isOpen */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      {/* Drawer - always rendered, position controlled by translate-x */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-56 flex flex-col border-r bg-background transition-transform md:hidden ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Optional top content (e.g., embedded project selector) */}
        {topContent && (
          <div className="border-b px-4 py-4">
            {topContent}
          </div>
        )}

        {/* Sidebar content */}
        {children}
      </aside>
    </>
  )
}
