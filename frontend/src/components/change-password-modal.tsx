"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, ApiError } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

const schema = z.object({
  current_password: z.string().min(1, "Současné heslo je povinné"),
  new_password: z.string().min(8, "Nové heslo musí mít alespoň 8 znaků"),
  confirm_password: z.string().min(1, "Potvrďte nové heslo"),
}).refine((d) => d.new_password === d.confirm_password, {
  message: "Hesla se neshodují",
  path: ["confirm_password"],
});

type FormData = z.infer<typeof schema>;

interface ChangePasswordModalProps {
  open: boolean;
  onClose: () => void;
}

export function ChangePasswordModal({ open, onClose }: ChangePasswordModalProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const handleClose = () => {
    reset();
    setServerError(null);
    setSuccess(false);
    onClose();
  };

  const onSubmit = async (data: FormData) => {
    setServerError(null);
    try {
      await api.post("/auth/change-password", {
        current_password: data.current_password,
        new_password: data.new_password,
      });
      setSuccess(true);
      reset();
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(err.detail);
      } else {
        setServerError("Chyba připojení k serveru");
      }
    }
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title="Změna hesla"
      description="Po změně hesla budou ostatní zařízení odhlášena"
      size="sm"
    >
      {success ? (
        <div className="space-y-4">
          <div className="rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-700">
            Heslo bylo úspěšně změněno.
          </div>
          <Button type="button" className="w-full" onClick={handleClose}>
            Zavřít
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="current_password">Současné heslo</Label>
            <Input
              id="current_password"
              type="password"
              autoComplete="current-password"
              {...register("current_password")}
            />
            {errors.current_password && (
              <p className="text-xs text-red-600">{errors.current_password.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="new_password">Nové heslo</Label>
            <Input
              id="new_password"
              type="password"
              autoComplete="new-password"
              {...register("new_password")}
            />
            {errors.new_password && (
              <p className="text-xs text-red-600">{errors.new_password.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="confirm_password">Potvrzení nového hesla</Label>
            <Input
              id="confirm_password"
              type="password"
              autoComplete="new-password"
              {...register("confirm_password")}
            />
            {errors.confirm_password && (
              <p className="text-xs text-red-600">{errors.confirm_password.message}</p>
            )}
          </div>

          {serverError && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {serverError}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={handleClose}>
              Zrušit
            </Button>
            <Button type="submit" loading={isSubmitting}>
              Změnit heslo
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
