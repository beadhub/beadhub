import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import {
  Shield,
  RefreshCw,
  RotateCcw,
  Clock,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  AlertTriangle,
  Plus,
  History,
  FileText,
  Users,
  Pencil,
  X,
  Check,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog"
import { Textarea } from "../components/ui/textarea"
import { Input } from "../components/ui/input"
import { Separator } from "../components/ui/separator"
import {
  type ApiClient,
  type ActivePolicy,
  type PolicyHistoryItem,
  type PolicyBundle,
  type Invariant,
  type RolePlaybook,
  type CreatePolicyResponse,
} from "../lib/api"
import { useStore } from "../hooks/useStore"
import { cn } from "../lib/utils"
import { Markdown } from "../components/Markdown"

function isAdminWriteForbidden(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status
  return status === 401 || status === 403
}

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) return "unknown"
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return "just now"
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 7) return `${diffDay}d ago`
  return date.toLocaleDateString()
}

function InvariantCard({ invariant }: { invariant: Invariant }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <Card>
      <CardContent className="p-4">
        <div
          className="flex items-start gap-2 cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4 mt-0.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 mt-0.5 text-muted-foreground" />
          )}
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{invariant.title}</span>
              <Badge variant="outline" className="text-xs">
                {invariant.id}
              </Badge>
            </div>
            {expanded && (
              <Markdown className="mt-2">{invariant.body_md}</Markdown>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function RoleCard({
  roleKey,
  role,
}: {
  roleKey: string
  role: RolePlaybook
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <Card>
      <CardContent className="p-4">
        <div
          className="flex items-start gap-2 cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4 mt-0.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 mt-0.5 text-muted-foreground" />
          )}
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              <span className="font-medium">{role.title}</span>
              <Badge variant="secondary" className="text-xs">
                {roleKey}
              </Badge>
            </div>
            {expanded && (
              <Markdown className="mt-2">{role.playbook_md}</Markdown>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function HistoryItem({
  item,
  onActivate,
  isActivating,
  readOnly,
}: {
  item: PolicyHistoryItem
  onActivate: () => void
  isActivating: boolean
  readOnly: boolean
}) {
  const api = useApi<ApiClient>()
  const [expanded, setExpanded] = useState(false)

  const {
    data: policyDetails,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["policy-by-id", item.policy_id],
    queryFn: () => api.getPolicyById(item.policy_id),
    enabled: expanded,
    staleTime: 60000,
  })

  return (
    <div className="border-b last:border-b-0">
      <div
        className="flex items-center justify-between py-2 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            {expanded ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            )}
            <Badge variant={item.is_active ? "default" : "outline"}>
              v{item.version}
            </Badge>
            {item.is_active && (
              <CheckCircle className="h-4 w-4 text-success" />
            )}
          </div>
          <span className="text-sm text-muted-foreground">
            <Clock className="h-3 w-3 inline mr-1" />
            {formatRelativeTime(item.created_at)}
          </span>
        </div>
        {!item.is_active && (
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              onActivate()
            }}
            disabled={isActivating || readOnly}
          >
            Activate
          </Button>
        )}
      </div>
      {expanded && (
        <div className="pb-4 pl-6">
          {isLoading && (
            <div className="text-sm text-muted-foreground flex items-center gap-2">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Loading policy details...
            </div>
          )}
          {Boolean(error) && (
            <div className="text-sm text-destructive flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              Failed to load policy: {(error as Error).message}
            </div>
          )}
          {policyDetails && (
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Invariants ({policyDetails.invariants.length})
                </h4>
                <div className="space-y-2">
                  {policyDetails.invariants.map((inv) => (
                    <div key={inv.id} className="text-sm border rounded p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium">{inv.title}</span>
                        <Badge variant="outline" className="text-xs">
                          {inv.id}
                        </Badge>
                      </div>
                      <Markdown className="text-muted-foreground">
                        {inv.body_md}
                      </Markdown>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  Role Playbooks ({Object.keys(policyDetails.roles).length})
                </h4>
                <div className="space-y-2">
                  {Object.entries(policyDetails.roles).map(([key, role]) => (
                    <div key={key} className="text-sm border rounded p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium">{role.title}</span>
                        <Badge variant="secondary" className="text-xs">
                          {key}
                        </Badge>
                      </div>
                      <Markdown className="text-muted-foreground">
                        {role.playbook_md}
                      </Markdown>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface ActivatePolicyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  target: PolicyHistoryItem | null
  onConfirm: () => void
  isPending: boolean
  error: unknown
}

function ActivatePolicyDialog({
  open,
  onOpenChange,
  target,
  onConfirm,
  isPending,
  error,
}: ActivatePolicyDialogProps) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (isPending) return
        onOpenChange(nextOpen)
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Activate policy version?</AlertDialogTitle>
          <AlertDialogDescription>
            This changes the active policy for the entire project. All
            workspaces/agents will see the new policy.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {target && (
          <div className="text-sm">
            You are about to activate <Badge variant="outline">v{target.version}</Badge>.
          </div>
        )}

        {Boolean(error) && (
          <p className="text-sm text-destructive">
            Failed to activate: {(error as Error).message}
          </p>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={!target || isPending}
            onClick={(e) => {
              e.preventDefault()
              onConfirm()
            }}
          >
            {isPending ? "Activating..." : "Activate"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

interface ResetPolicyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  isPending: boolean
  error: unknown
}

function ResetPolicyDialog({
  open,
  onOpenChange,
  onConfirm,
  isPending,
  error,
}: ResetPolicyDialogProps) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (isPending) return
        onOpenChange(nextOpen)
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Reset policy to defaults?</AlertDialogTitle>
          <AlertDialogDescription>
            This creates a new policy version from the default seed and activates
            it for the entire project. Previous versions remain in history.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {Boolean(error) && (
          <p className="text-sm text-destructive">
            Failed to reset: {(error as Error).message}
          </p>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={isPending}
            onClick={(e) => {
              e.preventDefault()
              onConfirm()
            }}
          >
            {isPending ? "Resetting..." : "Reset to Defaults"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

interface EditPolicyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentPolicy: ActivePolicy | null
  onSuccess: (created: CreatePolicyResponse) => void
  onAdminWriteForbidden: () => void
}

function EditPolicyDialog({
  open,
  onOpenChange,
  currentPolicy,
  onSuccess,
  onAdminWriteForbidden,
}: EditPolicyDialogProps) {
  const api = useApi<ApiClient>()
  const queryClient = useQueryClient()
  const [invariants, setInvariants] = useState<Invariant[]>([])
  const [roles, setRoles] = useState<Record<string, RolePlaybook>>({})
  const [newInvariantId, setNewInvariantId] = useState("")
  const [newInvariantTitle, setNewInvariantTitle] = useState("")
  const [newInvariantBody, setNewInvariantBody] = useState("")
  const [newRoleKey, setNewRoleKey] = useState("")
  const [newRoleTitle, setNewRoleTitle] = useState("")
  const [newRolePlaybook, setNewRolePlaybook] = useState("")
  const [activeTab, setActiveTab] = useState("invariants")
  const [editingInvariantId, setEditingInvariantId] = useState<string | null>(null)
  const [editingRoleKey, setEditingRoleKey] = useState<string | null>(null)
  const [editInvariant, setEditInvariant] = useState<Invariant | null>(null)
  const [editRole, setEditRole] = useState<{ key: string; role: RolePlaybook } | null>(null)

  // Track previous open state to detect when dialog opens
  const prevOpenRef = useRef(false)

  // Initialize from current policy only when dialog OPENS (false → true)
  // This prevents resetting state when currentPolicy refetches while dialog is open
  useEffect(() => {
    const justOpened = open && !prevOpenRef.current
    if (justOpened && currentPolicy) {
      setInvariants([...currentPolicy.invariants])
      setRoles({ ...currentPolicy.roles })
    }
    prevOpenRef.current = open
  }, [open, currentPolicy])

  const createMutation = useMutation({
    mutationFn: async (bundle: PolicyBundle) => {
      return api.createPolicy(bundle, currentPolicy?.policy_id)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["policy"] })
      queryClient.invalidateQueries({ queryKey: ["policy-history"] })
      onOpenChange(false)
      onSuccess(data)
    },
    onError: (err) => {
      if (isAdminWriteForbidden(err)) onAdminWriteForbidden()
    },
  })

  const handleAddInvariant = () => {
    if (newInvariantId && newInvariantTitle) {
      setInvariants([
        ...invariants,
        { id: newInvariantId, title: newInvariantTitle, body_md: newInvariantBody },
      ])
      setNewInvariantId("")
      setNewInvariantTitle("")
      setNewInvariantBody("")
    }
  }

  const handleRemoveInvariant = (id: string) => {
    setInvariants(invariants.filter((inv) => inv.id !== id))
  }

  const handleAddRole = () => {
    if (newRoleKey && newRoleTitle) {
      setRoles({
        ...roles,
        [newRoleKey]: { title: newRoleTitle, playbook_md: newRolePlaybook },
      })
      setNewRoleKey("")
      setNewRoleTitle("")
      setNewRolePlaybook("")
    }
  }

  const handleRemoveRole = (key: string) => {
    const newRoles = { ...roles }
    delete newRoles[key]
    setRoles(newRoles)
  }

  const handleStartEditInvariant = (inv: Invariant) => {
    setEditingInvariantId(inv.id)
    setEditInvariant({ ...inv })
  }

  const handleCancelEditInvariant = () => {
    setEditingInvariantId(null)
    setEditInvariant(null)
  }

  const handleSaveEditInvariant = () => {
    if (!editInvariant || !editingInvariantId) return
    setInvariants(
      invariants.map((inv) =>
        inv.id === editingInvariantId ? editInvariant : inv
      )
    )
    setEditingInvariantId(null)
    setEditInvariant(null)
  }

  const handleStartEditRole = (key: string, role: RolePlaybook) => {
    setEditingRoleKey(key)
    setEditRole({ key, role: { ...role } })
  }

  const handleCancelEditRole = () => {
    setEditingRoleKey(null)
    setEditRole(null)
  }

  const handleSaveEditRole = () => {
    if (!editRole || !editingRoleKey) return
    const newRoles = { ...roles }
    // If key changed, remove old key
    if (editRole.key !== editingRoleKey) {
      delete newRoles[editingRoleKey]
    }
    newRoles[editRole.key] = editRole.role
    setRoles(newRoles)
    setEditingRoleKey(null)
    setEditRole(null)
  }

  // Check if there's unsaved form content
  const hasUnsavedInvariant = newInvariantId.trim() || newInvariantTitle.trim() || newInvariantBody.trim()
  const hasUnsavedRole = newRoleKey.trim() || newRoleTitle.trim() || newRolePlaybook.trim()
  const hasUnsavedContent = hasUnsavedInvariant || hasUnsavedRole

  const handleSave = () => {
    const bundle: PolicyBundle = {
      invariants,
      roles,
      adapters: currentPolicy?.adapters || {},
    }
    createMutation.mutate(bundle)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create New Policy Version</DialogTitle>
          <DialogDescription>
            Create a new policy version based on the current active policy.
            The new version will not be activated automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="p-4 bg-warning/10 border border-warning/20 rounded-md flex items-start gap-2">
          <AlertTriangle className="h-5 w-5 text-warning shrink-0 mt-0.5" />
          <div className="text-sm">
            <strong>Security Notice:</strong> Policy content is visible to all
            agents in the project. Do not include secrets, API keys, or
            sensitive credentials in invariants or role playbooks.
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="invariants">
              Invariants ({invariants.length})
            </TabsTrigger>
            <TabsTrigger value="roles">Roles ({Object.keys(roles).length})</TabsTrigger>
          </TabsList>

          <TabsContent value="invariants" className="space-y-4">
            <div className="space-y-2">
              {invariants.map((inv) => (
                <div key={inv.id} className="border rounded">
                  {editingInvariantId === inv.id && editInvariant ? (
                    <div className="p-4 space-y-3 bg-muted/30">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-sm font-medium">ID</label>
                          <Input
                            value={editInvariant.id}
                            onChange={(e) =>
                              setEditInvariant({ ...editInvariant, id: e.target.value })
                            }
                          />
                        </div>
                        <div>
                          <label className="text-sm font-medium">Title</label>
                          <Input
                            value={editInvariant.title}
                            onChange={(e) =>
                              setEditInvariant({ ...editInvariant, title: e.target.value })
                            }
                          />
                        </div>
                      </div>
                      <div>
                        <label className="text-sm font-medium">Body (Markdown)</label>
                        <Textarea
                          value={editInvariant.body_md}
                          onChange={(e) =>
                            setEditInvariant({ ...editInvariant, body_md: e.target.value })
                          }
                          rows={8}
                          className="font-mono text-sm"
                        />
                      </div>
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleCancelEditInvariant}
                        >
                          <X className="h-4 w-4 mr-1" />
                          Cancel
                        </Button>
                        <Button size="sm" onClick={handleSaveEditInvariant}>
                          <Check className="h-4 w-4 mr-1" />
                          Save
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2 p-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{inv.id}</Badge>
                          <span className="font-medium">{inv.title}</span>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {inv.body_md}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleStartEditInvariant(inv)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => handleRemoveInvariant(inv.id)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <Separator />

            <div className="space-y-3">
              <h4 className="font-medium">Add Invariant</h4>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">ID</label>
                  <Input
                    placeholder="e.g., security.no-secrets"
                    value={newInvariantId}
                    onChange={(e) => setNewInvariantId(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Title</label>
                  <Input
                    placeholder="e.g., No secrets in code"
                    value={newInvariantTitle}
                    onChange={(e) => setNewInvariantTitle(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">Body (Markdown)</label>
                <Textarea
                  placeholder="Describe the invariant..."
                  value={newInvariantBody}
                  onChange={(e) => setNewInvariantBody(e.target.value)}
                  rows={6}
                  className="font-mono text-sm"
                />
              </div>
              <Button variant="outline" size="sm" onClick={handleAddInvariant}>
                <Plus className="h-4 w-4 mr-1" />
                Add Invariant
              </Button>
            </div>
          </TabsContent>

          <TabsContent value="roles" className="space-y-4">
            <div className="space-y-2">
              {Object.entries(roles).map(([key, role]) => (
                <div key={key} className="border rounded">
                  {editingRoleKey === key && editRole ? (
                    <div className="p-4 space-y-3 bg-muted/30">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-sm font-medium">Key</label>
                          <Input
                            value={editRole.key}
                            onChange={(e) =>
                              setEditRole({ ...editRole, key: e.target.value })
                            }
                          />
                        </div>
                        <div>
                          <label className="text-sm font-medium">Title</label>
                          <Input
                            value={editRole.role.title}
                            onChange={(e) =>
                              setEditRole({
                                ...editRole,
                                role: { ...editRole.role, title: e.target.value },
                              })
                            }
                          />
                        </div>
                      </div>
                      <div>
                        <label className="text-sm font-medium">Playbook (Markdown)</label>
                        <Textarea
                          value={editRole.role.playbook_md}
                          onChange={(e) =>
                            setEditRole({
                              ...editRole,
                              role: { ...editRole.role, playbook_md: e.target.value },
                            })
                          }
                          rows={12}
                          className="font-mono text-sm"
                        />
                      </div>
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleCancelEditRole}
                        >
                          <X className="h-4 w-4 mr-1" />
                          Cancel
                        </Button>
                        <Button size="sm" onClick={handleSaveEditRole}>
                          <Check className="h-4 w-4 mr-1" />
                          Save
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2 p-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary">{key}</Badge>
                          <span className="font-medium">{role.title}</span>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {role.playbook_md}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleStartEditRole(key, role)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => handleRemoveRole(key)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <Separator />

            <div className="space-y-3">
              <h4 className="font-medium">Add Role</h4>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">Key</label>
                  <Input
                    placeholder="e.g., backend-dev"
                    value={newRoleKey}
                    onChange={(e) => setNewRoleKey(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Title</label>
                  <Input
                    placeholder="e.g., Backend Developer"
                    value={newRoleTitle}
                    onChange={(e) => setNewRoleTitle(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">Playbook (Markdown)</label>
                <Textarea
                  placeholder="Describe the role's responsibilities..."
                  value={newRolePlaybook}
                  onChange={(e) => setNewRolePlaybook(e.target.value)}
                  rows={10}
                  className="font-mono text-sm"
                />
              </div>
              <Button variant="outline" size="sm" onClick={handleAddRole}>
                <Plus className="h-4 w-4 mr-1" />
                Add Role
              </Button>
            </div>
          </TabsContent>
        </Tabs>

        {createMutation.isError && (
          <p className="text-sm text-destructive">
            Failed to create policy: {(createMutation.error as Error).message}
          </p>
        )}

        {hasUnsavedContent && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-md flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="text-sm text-amber-800 dark:text-amber-200">
              You have unsaved {hasUnsavedInvariant && hasUnsavedRole ? "invariant and role" : hasUnsavedInvariant ? "invariant" : "role"} form content.
              Click <strong>Add {hasUnsavedInvariant ? "Invariant" : "Role"}</strong> to include it, or clear the form before creating.
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={createMutation.isPending}>
            {createMutation.isPending ? "Creating..." : "Create Version"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function PoliciesPage() {
  const api = useApi<ApiClient>()
  const { dashboardIdentity } = useStore()
  const queryClient = useQueryClient()
  const [readOnlyMode, setReadOnlyMode] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [activateDialogOpen, setActivateDialogOpen] = useState(false)
  const [resetDialogOpen, setResetDialogOpen] = useState(false)
  const [activateTarget, setActivateTarget] = useState<PolicyHistoryItem | null>(
    null
  )
  const [activeTab, setActiveTab] = useState("policy")
  const [newlyCreatedPolicy, setNewlyCreatedPolicy] = useState<CreatePolicyResponse | null>(null)

  const {
    data: policy,
    isLoading: policyLoading,
    error: policyError,
    refetch: refetchPolicy,
  } = useQuery({
    queryKey: ["policy"],
    queryFn: () => api.getActivePolicy(),
    enabled: !!dashboardIdentity,
    refetchInterval: 30000,
  })

  const {
    data: historyData,
    isLoading: historyLoading,
    refetch: refetchHistory,
  } = useQuery({
    queryKey: ["policy-history"],
    queryFn: () => api.getPolicyHistory(10),
    enabled: !!dashboardIdentity,
  })

  const activateMutation = useMutation({
    mutationFn: async (policyId: string) => {
      return api.activatePolicy(policyId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policy"] })
      queryClient.invalidateQueries({ queryKey: ["policy-history"] })
    },
    onError: (err) => {
      if (isAdminWriteForbidden(err)) setReadOnlyMode(true)
    },
  })

  const resetMutation = useMutation({
    mutationFn: async () => {
      return api.resetPolicyToDefault()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policy"] })
      queryClient.invalidateQueries({ queryKey: ["policy-history"] })
      setResetDialogOpen(false)
    },
    onError: (err) => {
      if (isAdminWriteForbidden(err)) setReadOnlyMode(true)
    },
  })

  const handleAdminWriteForbidden = () => {
    setReadOnlyMode(true)
    setEditDialogOpen(false)
    setActivateDialogOpen(false)
    setResetDialogOpen(false)
  }

  const handleRefresh = () => {
    refetchPolicy()
    refetchHistory()
  }

  const handlePolicyCreated = (created: CreatePolicyResponse) => {
    setNewlyCreatedPolicy(created)
    setActiveTab("history")
    refetchPolicy()
    refetchHistory()
  }

  const handleActivateNewPolicy = () => {
    if (!newlyCreatedPolicy) return
    activateMutation.mutate(newlyCreatedPolicy.policy_id, {
      onSuccess: () => {
        setNewlyCreatedPolicy(null)
      },
    })
  }

  const handleDismissCreationSuccess = () => {
    setNewlyCreatedPolicy(null)
  }

  if (!dashboardIdentity) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Policies</h1>
            <p className="text-sm text-muted-foreground">Project policy configuration</p>
          </div>
        </div>
        <Card>
          <CardContent className="p-8 text-center">
            <Shield className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
            <p className="text-muted-foreground">No workspace available. Register a workspace to view policies.</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Policies</h1>
          <p className="text-sm text-muted-foreground">
            {policy ? `Version ${policy.version}` : "Loading..."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="text-destructive"
            onClick={() => {
              resetMutation.reset()
              setResetDialogOpen(true)
            }}
            disabled={readOnlyMode || resetMutation.isPending}
          >
            <RotateCcw className="h-4 w-4 mr-1" />
            Reset to Defaults
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditDialogOpen(true)}
            disabled={readOnlyMode}
          >
            <Plus className="h-4 w-4 mr-1" />
            New Version
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={policyLoading}
          >
            <RefreshCw className={cn("h-4 w-4", policyLoading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* Error State */}
      {policyError && (
        <Card className="border-destructive">
          <CardContent className="p-4">
            <p className="text-sm text-destructive">
              Failed to load policy: {(policyError as Error).message}
            </p>
          </CardContent>
        </Card>
      )}

      {readOnlyMode && (
        <Card className="border-warning/50 bg-warning/5">
          <CardContent className="p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-warning shrink-0 mt-0.5" />
            <div className="text-sm">
              <div className="font-medium">Read-only mode</div>
              <div className="text-muted-foreground mt-1">
                This dashboard is not permitted to create, activate, or reset
                policy versions. Viewing is still available. To enable admin
                actions, run the dashboard with a valid API key (or use an
                embedded dashboard which injects auth headers).
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Loading State */}
      {policyLoading && !policy && (
        <div className="text-center py-12 text-muted-foreground">
          Loading policy...
        </div>
      )}

      {/* Main Content */}
      {policy && (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="policy" className="gap-2">
              <FileText className="h-4 w-4" />
              Active Policy
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2">
              <History className="h-4 w-4" />
              History
            </TabsTrigger>
          </TabsList>

          <TabsContent value="policy" className="space-y-6 mt-4">
            {/* Policy Metadata */}
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Shield className="h-4 w-4" />
                    Active Policy
                  </CardTitle>
                  <Badge variant="outline">v{policy.version}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-muted-foreground">
                  <Clock className="h-3 w-3 inline mr-1" />
                  Last updated {formatRelativeTime(policy.updated_at)}
                </div>
              </CardContent>
            </Card>

            {/* Invariants */}
            <div>
              <h3 className="text-lg font-medium mb-3 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Invariants ({policy.invariants.length})
              </h3>
              {policy.invariants.length === 0 ? (
                <Card>
                  <CardContent className="p-4 text-center text-muted-foreground">
                    No invariants defined
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-2">
                  {policy.invariants.map((inv) => (
                    <InvariantCard key={inv.id} invariant={inv} />
                  ))}
                </div>
              )}
            </div>

            {/* Roles */}
            <div>
              <h3 className="text-lg font-medium mb-3 flex items-center gap-2">
                <Users className="h-4 w-4" />
                Role Playbooks ({Object.keys(policy.roles).length})
              </h3>
              {Object.keys(policy.roles).length === 0 ? (
                <Card>
                  <CardContent className="p-4 text-center text-muted-foreground">
                    No roles defined
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-2">
                  {Object.entries(policy.roles).map(([key, role]) => (
                    <RoleCard
                      key={key}
                      roleKey={key}
                      role={role}
                    />
                  ))}
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="history" className="mt-4">
            {/* Success banner after creating new version */}
            {newlyCreatedPolicy && (
              <Card className="mb-4 border-green-500/50 bg-green-500/5">
                <CardContent className="p-4 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
                    <div className="text-sm">
                      <span className="font-medium">
                        Version {newlyCreatedPolicy.version} created successfully.
                      </span>{" "}
                      <span className="text-muted-foreground">
                        Activate it to make it the active policy for all agents.
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleDismissCreationSuccess}
                    >
                      Dismiss
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleActivateNewPolicy}
                      disabled={activateMutation.isPending}
                    >
                      {activateMutation.isPending ? "Activating..." : "Activate Now"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <History className="h-4 w-4" />
                  Version History
                </CardTitle>
              </CardHeader>
              <CardContent>
                {historyLoading ? (
                  <div className="text-center py-4 text-muted-foreground">
                    Loading history...
                  </div>
                ) : historyData?.policies.length === 0 ? (
                  <div className="text-center py-4 text-muted-foreground">
                    No policy versions found
                  </div>
                ) : (
                  <div>
                    {historyData?.policies.map((item) => (
                      <HistoryItem
                        key={item.policy_id}
                        item={item}
                        onActivate={() => {
                          activateMutation.reset()
                          setActivateTarget(item)
                          setActivateDialogOpen(true)
                        }}
                        isActivating={activateMutation.isPending}
                        readOnly={readOnlyMode}
                      />
                    ))}
                  </div>
                )}
                {activateMutation.isError && (
                  <p className="mt-2 text-sm text-destructive">
                    Failed to activate: {(activateMutation.error as Error).message}
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      <ActivatePolicyDialog
        open={activateDialogOpen}
        onOpenChange={(open) => {
          setActivateDialogOpen(open)
          if (!open) {
            setActivateTarget(null)
            activateMutation.reset()
          }
        }}
        target={activateTarget}
        isPending={activateMutation.isPending}
        error={activateMutation.isError ? activateMutation.error : null}
        onConfirm={() => {
          if (!activateTarget) return
          activateMutation.mutate(activateTarget.policy_id, {
            onSuccess: () => {
              setActivateDialogOpen(false)
              setActivateTarget(null)
            },
            onError: (err) => {
              if (isAdminWriteForbidden(err)) handleAdminWriteForbidden()
            },
          })
        }}
      />

      <ResetPolicyDialog
        open={resetDialogOpen}
        onOpenChange={(open) => {
          setResetDialogOpen(open)
          if (!open) resetMutation.reset()
        }}
        isPending={resetMutation.isPending}
        error={resetMutation.isError ? resetMutation.error : null}
        onConfirm={() => {
          resetMutation.mutate(undefined, {
            onError: (err) => {
              if (isAdminWriteForbidden(err)) handleAdminWriteForbidden()
            },
          })
        }}
      />

      {/* Edit Dialog */}
      <EditPolicyDialog
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
        currentPolicy={policy || null}
        onSuccess={handlePolicyCreated}
        onAdminWriteForbidden={handleAdminWriteForbidden}
      />
    </div>
  )
}
