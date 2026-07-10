import { useEffect, useState } from "react";

import { countdown } from "@/lib/format";

/** Time left until expiry, corrected by the server clock so a wrong phone clock does not lie. */
export function Countdown({ expiresAt, serverTime }: { expiresAt: string; serverTime: string }) {
  const [skew] = useState(() => new Date(serverTime).getTime() - Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const left = new Date(expiresAt).getTime() - (now + skew);
  const urgent = left < 3 * 60 * 1000;
  return (
    <span className={urgent ? "tabular text-warn" : "tabular"} aria-live="off">
      {left > 0 ? countdown(left) : "0:00"}
    </span>
  );
}
