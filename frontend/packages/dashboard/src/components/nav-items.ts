import {
  Activity,
  Users,
  AlertTriangle,
  ListTodo,
  MessageSquare,
  MessageCircle,
  GitBranch,
  Shield,
} from 'lucide-react'
import type { NavItem } from './types'

export const navItems: NavItem[] = [
  // Overview
  { path: '/', label: 'Status', icon: Activity, group: 'overview' },
  // Coordination (most used)
  { path: '/tasks', label: 'Tasks', icon: ListTodo, group: 'coordination' },
  { path: '/claims', label: 'Claims', icon: GitBranch, group: 'coordination' },
  // Communication
  { path: '/messages', label: 'Mail', icon: MessageSquare, group: 'communication' },
  { path: '/chat', label: 'Chat', icon: MessageCircle, group: 'communication' },
  // Admin (seldom used)
  { path: '/workspaces', label: 'Workspaces', icon: Users, group: 'admin' },
  { path: '/escalations', label: 'Escalations', icon: AlertTriangle, group: 'admin' },
  { path: '/policies', label: 'Policies', icon: Shield, group: 'admin' },
]
