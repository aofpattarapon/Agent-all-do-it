"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Search,
  Shield,
  Trash2,
} from "lucide-react";

import { UserDetailDrawer } from "@/components/admin/user-detail-drawer";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAdminUsers } from "@/hooks";
import type { AdminUserRead } from "@/hooks/use-admin-users";
import { cn, getInitials } from "@/lib/utils";
import { toast } from "sonner";

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
type SortDir = "asc" | "desc";
type SortKey = "email" | "full_name" | "role" | "is_active" | "created_at";

export default function AdminUsersPage() {
  const { users, total, isLoading, fetchUsers, updateUser, deleteUser, impersonateUser } =
    useAdminUsers();
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<{ by: SortKey; dir: SortDir }>({
    by: "created_at",
    dir: "desc",
  });
  const [drawerUser, setDrawerUser] = useState<AdminUserRead | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [singleDeleteTarget, setSingleDeleteTarget] = useState<AdminUserRead | null>(null);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);

  // Reset to first page when filters change
  useEffect(() => {
    setPage(0);
  }, [search, pageSize, sort.by, sort.dir, roleFilter]);

  const load = useCallback(
    (pg: number, q: string, ps: number) => {
      fetchUsers({ skip: pg * ps, limit: ps, search: q || undefined });
    },
    [fetchUsers],
  );

  // Debounced fetch
  useEffect(() => {
    const timer = setTimeout(() => {
      load(page, search, pageSize);
    }, 300);
    return () => clearTimeout(timer);
  }, [load, page, search, pageSize, sort.by, sort.dir]);

  // Keep the drawer's user object in sync with updates from the hook.
  useEffect(() => {
    if (drawerUser) {
      const fresh = users.find((u) => u.id === drawerUser.id);
      if (fresh && fresh !== drawerUser) setDrawerUser(fresh);
    }
  }, [users, drawerUser]);

  const handleOpenUser = (user: AdminUserRead) => {
    setDrawerUser(user);
    setDrawerOpen(true);
  };

  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s.by === key
        ? { by: key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { by: key, dir: "desc" },
    );

  // Apply client-side sort + role filter over current page.
  const sortedFilteredUsers = useMemo(() => {
    let arr = [...users];
    if (roleFilter !== "all") {
      arr = arr.filter((u) => u.role === roleFilter);
    }
    arr.sort((a, b) => {
      const av = (a[sort.by] ?? "") as string | number | boolean;
      const bv = (b[sort.by] ?? "") as string | number | boolean;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [users, sort.by, sort.dir, roleFilter]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Selection
  const allPageSelected =
    sortedFilteredUsers.length > 0 && sortedFilteredUsers.every((u) => selected.has(u.id));
  const somePageSelected = sortedFilteredUsers.some((u) => selected.has(u.id));

  const toggleAll = () => {
    if (allPageSelected) {
      setSelected((s) => {
        const next = new Set(s);
        sortedFilteredUsers.forEach((u) => next.delete(u.id));
        return next;
      });
    } else {
      setSelected((s) => {
        const next = new Set(s);
        sortedFilteredUsers.forEach((u) => next.add(u.id));
        return next;
      });
    }
  };

  const toggleOne = (id: string) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBulkDelete = async () => {
    const count = selected.size;
    setIsBulkDeleting(true);
    // deleteUser from hook handles per-item toast; we just orchestrate.
    await Promise.allSettled(Array.from(selected).map((id) => deleteUser(id)));
    toast.success(`Deleted ${count} users`);
    setSelected(new Set());
    setBulkDeleteOpen(false);
    setIsBulkDeleting(false);
    load(page, search, pageSize);
  };

  const handleSingleDelete = async () => {
    if (!singleDeleteTarget) return;
    await deleteUser(singleDeleteTarget.id);
    setSingleDeleteTarget(null);
    load(page, search, pageSize);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="mb-6">
        <p className="text-foreground/55 font-mono text-[11px] tracking-wider uppercase">
          Users
        </p>
        <h2 className="font-display text-foreground mt-1 text-xl font-semibold tracking-tight [&_em]:font-accent [&_em]:font-normal [&_em]:italic">
          Everyone in <em>your workspace.</em>
        </h2>
        <p className="text-muted-foreground">
          Inspect, suspend, or impersonate any user in the workspace.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="Search by email or name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        {/* Role filter */}
        <Select value={roleFilter} onValueChange={setRoleFilter}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="All roles" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All roles</SelectItem>
            <SelectItem value="user">User</SelectItem>
            <SelectItem value="admin">Admin</SelectItem>
          </SelectContent>
        </Select>

        <Select value={String(pageSize)} onValueChange={(v) => setPageSize(Number(v))}>
          <SelectTrigger className="w-[110px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n} / page
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {selected.size > 0 && (
          <Button size="sm" variant="destructive" onClick={() => setBulkDeleteOpen(true)}>
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Delete {selected.size}
          </Button>
        )}
      </div>

      <div className="text-muted-foreground mb-2 text-xs">{total} total</div>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  checked={allPageSelected}
                  data-state={somePageSelected && !allPageSelected ? "indeterminate" : undefined}
                  onCheckedChange={toggleAll}
                  aria-label="Select all"
                />
              </TableHead>
              <SortableHead
                active={sort.by === "email"}
                dir={sort.dir}
                onClick={() => toggleSort("email")}
              >
                User
              </SortableHead>
              <SortableHead
                active={sort.by === "role"}
                dir={sort.dir}
                onClick={() => toggleSort("role")}
              >
                Role
              </SortableHead>
              <SortableHead
                active={sort.by === "is_active"}
                dir={sort.dir}
                onClick={() => toggleSort("is_active")}
              >
                Status
              </SortableHead>
              <SortableHead
                active={sort.by === "created_at"}
                dir={sort.dir}
                onClick={() => toggleSort("created_at")}
              >
                Joined
              </SortableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && users.length === 0
              ? Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : sortedFilteredUsers.map((u) => (
                  <TableRow
                    key={u.id}
                    className={cn(
                      "cursor-pointer",
                      selected.has(u.id) && "bg-muted/40",
                    )}
                    onClick={() => handleOpenUser(u)}
                  >
                    <TableCell>
                      <Checkbox
                        checked={selected.has(u.id)}
                        onCheckedChange={() => toggleOne(u.id)}
                        aria-label={`Select ${u.email}`}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex min-w-0 items-center gap-3">
                        <Avatar className="h-8 w-8 shrink-0">
                          <AvatarImage src={`/api/users/avatar/${u.id}`} alt={u.email} />
                          <AvatarFallback className="text-[10px]">
                            {getInitials(u.full_name || u.email)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <p className="text-foreground truncate text-sm font-medium">
                            {u.full_name || u.email.split("@")[0]}
                          </p>
                          <p className="text-muted-foreground truncate text-xs">{u.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm capitalize">{u.role}</span>
                        {u.is_app_admin && (
                          <Badge variant="default" className="gap-0.5">
                            <Shield className="h-2.5 w-2.5" />
                            App
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {u.is_active ? (
                        <Badge variant="default">Active</Badge>
                      ) : (
                        <Badge variant="destructive">Suspended</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {new Date(u.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenUser(u);
                          }}
                        >
                          Inspect
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSingleDeleteTarget(u);
                          }}
                          title="Delete user"
                        >
                          <Trash2 className="text-destructive h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
            {!isLoading && users.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="text-muted-foreground py-8 text-center"
                >
                  {search ? `No users match "${search}".` : "No users yet."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <PaginationBar
        page={page}
        pageSize={pageSize}
        total={total}
        totalPages={totalPages}
        isLoading={isLoading}
        onPrev={() => setPage((p) => Math.max(0, p - 1))}
        onNext={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
      />

      <UserDetailDrawer
        user={drawerUser}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        onUpdate={updateUser}
        onDelete={deleteUser}
        onImpersonate={impersonateUser}
      />

      {/* Single delete confirmation */}
      <AlertDialog
        open={!!singleDeleteTarget}
        onOpenChange={(v) => { if (!v) setSingleDeleteTarget(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete user?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete <strong>{singleDeleteTarget?.email}</strong>,
              their conversations, and credit balance. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleSingleDelete}
            >
              Delete User
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk delete confirmation */}
      <AlertDialog open={bulkDeleteOpen} onOpenChange={setBulkDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selected.size} users?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete {selected.size} users, their conversations, and
              credit balances. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleBulkDelete}
              aria-disabled={isBulkDeleting}
            >
              {isBulkDeleting ? "Deleting…" : `Delete ${selected.size} Users`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function SortableHead({
  active,
  dir,
  onClick,
  children,
}: {
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "hover:text-foreground inline-flex items-center gap-1 text-left transition-colors",
          active && "text-foreground",
        )}
      >
        {children}
        <Icon className={cn("h-3 w-3", !active && "opacity-40")} aria-hidden />
      </button>
    </TableHead>
  );
}

function PaginationBar({
  page,
  pageSize,
  total,
  totalPages,
  isLoading,
  onPrev,
  onNext,
}: {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  isLoading: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (total === 0) return null;
  const start = page * pageSize + 1;
  const end = Math.min(total, (page + 1) * pageSize);
  return (
    <div className="flex items-center justify-between border-t px-4 py-3">
      <span className="text-muted-foreground text-sm">
        {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={onPrev}
          disabled={page === 0 || isLoading}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="text-muted-foreground px-2 text-sm">
          {page + 1} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={onNext}
          disabled={page >= totalPages - 1 || isLoading}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
