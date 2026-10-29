// Asks for the access code when a live run gets a 401, instead of the browser's prompt().
import { useEffect, useRef, useState } from "react";
import * as stylex from "@stylexjs/stylex";
import { onCodeNeeded } from "@/api";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { TextInput } from "@astryxdesign/core/TextInput";
import { text } from "@/styles";

const s = stylex.create({ actions: { display: "flex", justifyContent: "flex-end", gap: 8 } });

export function AccessCode() {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const resolve = useRef<(c: string | null) => void>(() => {});

  useEffect(() => onCodeNeeded(() => new Promise((res) => { resolve.current = res; setCode(""); setOpen(true); })), []);
  const close = (value: string | null) => { setOpen(false); resolve.current(value); };

  return (
    <Dialog isOpen={open} onOpenChange={(o) => !o && close(null)} purpose="form" width={440}>
      <DialogHeader title="Live runs need the access code" onOpenChange={(o) => !o && close(null)}
                    subtitle="Live runs call the models and cost money, so they're limited. The demo is free to try." />
      <form onSubmit={(e) => { e.preventDefault(); close(code); }} {...stylex.props(text.stack)}>
        <TextInput type="password" label="Access code" hasAutoFocus value={code} onChange={setCode} />
        <div {...stylex.props(s.actions)}>
          <Button variant="secondary" label="Cancel" onClick={() => close(null)} />
          <Button type="submit" variant="primary" label="Continue" isDisabled={!code.trim()} />
        </div>
      </form>
    </Dialog>
  );
}
