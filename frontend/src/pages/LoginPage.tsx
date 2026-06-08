import { FormEvent, useState } from "react";
import { LockKeyhole } from "lucide-react";

type Props = {
  onLogin: (secret: string) => Promise<void>;
};

export function LoginPage({ onLogin }: Props) {
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await onLogin(secret);
    } catch {
      setError("Invalid access secret");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-field px-4">
      <form className="w-full max-w-sm rounded border border-line bg-white p-6 shadow-sm" onSubmit={submit}>
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded bg-pine text-white">
            <LockKeyhole size={20} />
          </div>
          <div>
            <h1 className="text-xl font-semibold">CB Failed Assistant</h1>
            <p className="text-sm text-ink/60">Protected workspace</p>
          </div>
        </div>
        <label className="mb-2 block text-sm font-medium" htmlFor="secret">
          Access secret
        </label>
        <input
          id="secret"
          type="password"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          className="mb-3 w-full rounded border border-line px-3 py-2 outline-none focus:border-pine"
        />
        {error && <p className="mb-3 text-sm text-coral">{error}</p>}
        <button className="w-full rounded bg-pine px-4 py-2 font-medium text-white disabled:opacity-60" disabled={loading}>
          {loading ? "Checking..." : "Login"}
        </button>
      </form>
    </div>
  );
}

