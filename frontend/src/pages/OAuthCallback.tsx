import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { authAPI } from "../lib/api";

export function OAuthCallback() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const { login } = useAuth();

    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const provider = searchParams.get("provider");
        const code = searchParams.get("code");
        const state = searchParams.get("state");

        if (!provider || !code || !state) {
            setError("Missing OAuth parameters in URL.");
            return;
        }

        const exchangeCode = async () => {
            try {
                const res = await authAPI.oauthCallback(provider, code, state);
                login(res.user);
                navigate(res.user.role === "instructor" ? "/exams" : "/");
            } catch (err: any) {
                console.error("OAuth exchange failed", err);
                setError("Failed to authenticate. Please try again.");
            }
        };

        exchangeCode();
    }, [searchParams, navigate, login]);

    return (
        <div className="flex h-screen w-full items-center justify-center p-4">
            {error ? (
                <div className="max-w-md w-full p-6 glass rounded-xl border border-destructive/20 text-center">
                    <p className="text-destructive font-medium mb-4">{error}</p>
                    <button
                        onClick={() => navigate("/auth")}
                        className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-md transition-colors"
                    >
                        Return to Login
                    </button>
                </div>
            ) : (
                <div className="flex flex-col items-center gap-4 text-center">
                    <Loader2 className="h-10 w-10 animate-spin text-primary" />
                    <h2 className="text-xl font-semibold">Authenticating...</h2>
                    <p className="text-muted-foreground">Please wait while we log you in securely.</p>
                </div>
            )}
        </div>
    );
}
