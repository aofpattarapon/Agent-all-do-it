import { AuthGuard } from "@/components/layout/auth-guard";
import { CommandPalette } from "@/components/layout/command-palette";
import { ConsoleShellWrapper } from "@/components/layout/console-shell-wrapper";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <ConsoleShellWrapper>
        {children}
      </ConsoleShellWrapper>
      <CommandPalette />
    </AuthGuard>
  );
}
