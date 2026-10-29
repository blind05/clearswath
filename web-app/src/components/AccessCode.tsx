// Asks for the access code when a live run gets a 401, instead of the browser's prompt().
import { useEffect, useRef, useState } from "react";
import { onCodeNeeded } from "@/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export function AccessCode() {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const resolve = useRef<(c: string | null) => void>(() => {});

  useEffect(() => onCodeNeeded(() => new Promise((res) => { resolve.current = res; setCode(""); setOpen(true); })), []);
  const close = (value: string | null) => { setOpen(false); resolve.current(value); };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Live runs need the access code</DialogTitle>
          <DialogDescription>Live runs call the models and cost money, so they're limited. The demo is free to try.</DialogDescription>
        </DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); close(code); }} className="grid gap-3">
          <Input autoFocus type="password" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Access code" />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => close(null)}>Cancel</Button>
            <Button type="submit" disabled={!code.trim()}>Continue</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
