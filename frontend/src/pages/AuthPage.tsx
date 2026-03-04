import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { BrainCircuit, Loader2, Github } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { authAPI } from "../lib/api";

import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../components/ui/card";
import { AnimatedText } from "../components/ui/animated-underline-text-one";
import ShaderBackground from "../components/ui/shader-background";

export function AuthPage() {
    const [isLogin, setIsLogin] = useState(true);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [providers, setProviders] = useState<{ [key: string]: { label: string; configured: boolean } }>({});

    const { login } = useAuth();
    const navigate = useNavigate();

    // Form State
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [email, setEmail] = useState("");
    const [role, setRole] = useState<"student" | "instructor">("student");

    useEffect(() => {
        // Check available OAuth providers
        authAPI.getOAuthProviders()
            .then((res: any) => {
                setProviders(res.providers || {});
            })
            .catch((err: any) => {
                console.error("Failed to load providers", err);
            });
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            let user;
            if (isLogin) {
                user = await authAPI.login({ username, password });
            } else {
                user = await authAPI.register({ username, password, role, email: email || undefined });
            }

            login(user);
            navigate(user.role === "instructor" ? "/exams" : "/");
        } catch (err: any) {
            setError(err.response?.data?.detail || "Authentication failed. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const handleOAuthLogin = async (provider: string) => {
        try {
            const res = await authAPI.startOAuth(provider, role);
            if (res.authorize_url) {
                window.location.href = res.authorize_url;
            }
        } catch (err) {
            setError(`Failed to start ${provider} login.`);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center p-4">
            <ShaderBackground />

            <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="z-10 w-full max-w-md"
            >
                <div className="flex flex-col items-center mb-8">
                    <motion.div
                        initial={{ rotate: -180, scale: 0 }}
                        animate={{ rotate: 0, scale: 1 }}
                        transition={{ type: "spring", stiffness: 200, damping: 20, delay: 0.2 }}
                        className="p-3 glass rounded-2xl mb-2"
                    >
                        <BrainCircuit className="h-10 w-10 text-primary" />
                    </motion.div>
                    <AnimatedText
                        text="EduGen"
                        className="gap-0"
                        textClassName="text-3xl font-bold tracking-tight text-center"
                        underlineClassName="text-primary/80"
                    />
                    <h1 className="text-2xl font-semibold tracking-tight text-center mt-4">Welcome back</h1>
                    <p className="text-muted-foreground mt-2">Sign in to continue your learning journey</p>
                </div>

                <Card className="glass-panel border-white/5">
                    <CardHeader>
                        <CardTitle>{isLogin ? "Sign In" : "Create Account"}</CardTitle>
                        <CardDescription>
                            {isLogin ? "Enter your credentials to access your account" : "Sign up for a new EduGen account"}
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {error && (
                            <div className="mb-4 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-destructive text-sm text-center">
                                {error}
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="username">Username</Label>
                                <Input
                                    id="username"
                                    placeholder="johndoe"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    required
                                    className="bg-black/50 border-white/10 focus:border-primary/50"
                                />
                            </div>

                            {!isLogin && (
                                <div className="space-y-2">
                                    <Label htmlFor="email">Email (Optional)</Label>
                                    <Input
                                        id="email"
                                        type="email"
                                        placeholder="john@example.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="bg-black/50 border-white/10 focus:border-primary/50"
                                    />
                                </div>
                            )}

                            <div className="space-y-2">
                                <Label htmlFor="password">Password</Label>
                                <Input
                                    id="password"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    className="bg-black/50 border-white/10 focus:border-primary/50"
                                    minLength={6}
                                />
                            </div>

                            {!isLogin && (
                                <div className="space-y-2">
                                    <Label>I am a...</Label>
                                    <div className="flex gap-4">
                                        <Label className="flex items-center gap-2 cursor-pointer p-3 rounded-md border border-white/10 hover:bg-white/5 w-full justify-center transition-colors">
                                            <input
                                                type="radio"
                                                name="role"
                                                value="student"
                                                checked={role === "student"}
                                                onChange={() => setRole("student")}
                                                className="accent-primary"
                                            />
                                            Student
                                        </Label>
                                        <Label className="flex items-center gap-2 cursor-pointer p-3 rounded-md border border-white/10 hover:bg-white/5 w-full justify-center transition-colors">
                                            <input
                                                type="radio"
                                                name="role"
                                                value="instructor"
                                                checked={role === "instructor"}
                                                onChange={() => setRole("instructor")}
                                                className="accent-primary"
                                            />
                                            Instructor
                                        </Label>
                                    </div>
                                </div>
                            )}

                            <Button
                                type="submit"
                                className="w-full bg-gradient-to-r from-primary to-cyan-500 hover:from-primary/90 hover:to-cyan-500/90 text-white font-semibold transition-all hover:scale-[1.02]"
                                disabled={loading}
                            >
                                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                {isLogin ? "Sign In" : "Sign Up"}
                            </Button>
                        </form>

                        {providers.google && providers.google.configured && (
                            <div className="mt-6">
                                <div className="relative">
                                    <div className="absolute inset-0 flex items-center">
                                        <span className="w-full border-t border-white/10" />
                                    </div>
                                    <div className="relative flex justify-center text-xs uppercase">
                                        <span className="bg-background px-2 text-muted-foreground">
                                            Or continue with
                                        </span>
                                    </div>
                                </div>

                                <div className="mt-4 flex gap-2">
                                    <Button
                                        variant="outline"
                                        type="button"
                                        className="w-full bg-black/50 border-white/10 hover:bg-white/5 transition-all hover:scale-[1.02]"
                                        onClick={() => handleOAuthLogin('google')}
                                    >
                                        Google
                                    </Button>
                                    {providers.github && providers.github.configured && (
                                        <Button
                                            variant="outline"
                                            type="button"
                                            className="w-full bg-black/50 border-white/10 hover:bg-white/5 transition-all hover:scale-[1.02]"
                                            onClick={() => handleOAuthLogin('github')}
                                        >
                                            <Github className="mr-2 h-4 w-4" />
                                            Github
                                        </Button>
                                    )}
                                </div>
                            </div>
                        )}
                    </CardContent>
                    <CardFooter className="flex justify-center border-t border-white/5 pt-4">
                        <button
                            onClick={() => setIsLogin(!isLogin)}
                            className="text-sm text-muted-foreground hover:text-primary transition-colors focus:outline-none"
                        >
                            {isLogin ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
                        </button>
                    </CardFooter>
                </Card>
            </motion.div>
        </div>
    );
}
