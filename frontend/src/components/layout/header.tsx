"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { UserResponse } from "@/types/api";

interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  const { data: user } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6">
      <h1 className="text-base font-semibold text-gray-900">{title}</h1>
      {user && (
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">{user.email}</span>
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 uppercase">
            {user.role}
          </span>
        </div>
      )}
    </header>
  );
}
