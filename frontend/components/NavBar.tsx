"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bot, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";

export function NavBar() {
  const { logout } = useAuth();
  const router = useRouter();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <nav className="flex items-center justify-between border-b bg-card px-6 py-3">
      <Link href="/runs" className="flex items-center gap-2 text-base font-semibold">
        <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Bot className="size-4" />
        </span>
        Agent Ops Dashboard
      </Link>
      <Button variant="ghost" size="sm" onClick={handleLogout}>
        <LogOut />
        Log out
      </Button>
    </nav>
  );
}
