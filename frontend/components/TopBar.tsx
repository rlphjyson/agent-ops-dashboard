"use client";

import { useRouter } from "next/navigation";
import { LogOut, Moon, Sun } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { Button } from "@/components/ui/button";

export function TopBar() {
  const { logout } = useAuth();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <header className="flex items-center justify-end gap-1 border-b px-4 py-2">
      <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle dark mode">
        {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </Button>
      <Button variant="ghost" size="sm" onClick={handleLogout}>
        <LogOut />
        Log out
      </Button>
    </header>
  );
}
