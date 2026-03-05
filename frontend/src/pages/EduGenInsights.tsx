import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Loader2, Sparkles, AlertCircle, Database, ChevronRight } from 'lucide-react';
import { instructorAPI } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';

const SUGGESTED_QUESTIONS = [
    "Who scored above 80 in Math?",
    "What is the average score in Physics?",
    "Which students failed Chemistry?",
    "Who are the top 5 students overall?"
];

export function EduGenInsights() {
    const [question, setQuestion] = useState("");
    const [isAsking, setIsAsking] = useState(false);
    const [result, setResult] = useState<{ sql: string, results: any[] | null, error: string | null } | null>(null);

    const handleAsk = async (e?: React.FormEvent, presetQuestion?: string) => {
        if (e) e.preventDefault();

        const query = presetQuestion || question;
        if (!query.trim()) return;

        if (presetQuestion) setQuestion(presetQuestion);
        setIsAsking(true);
        setResult(null);

        try {
            const res = await instructorAPI.ask(query);
            setResult(res);
        } catch (err: any) {
            setResult({
                sql: "",
                results: null,
                error: err.response?.data?.detail || "Failed to execute AI query"
            });
        } finally {
            setIsAsking(false);
        }
    };

    return (
        <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="text-center space-y-4 max-w-2xl mx-auto mt-8">
                <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: "spring", stiffness: 200, damping: 20 }}
                    className="mx-auto w-16 h-16 rounded-2xl glass flex items-center justify-center mb-6"
                >
                    <Sparkles className="h-8 w-8 text-primary" />
                </motion.div>

                <h1 className="text-4xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-primary via-cyan-400 to-primary bg-300% animate-gradient">
                    EduGen Insights AI
                </h1>
                <p className="text-muted-foreground text-lg">
                    Ask questions in plain English to instantly query your student analytics database using AI-powered Text-to-SQL.
                </p>
            </div>

            <Card className="glass-panel border-white/10 relative overflow-hidden shadow-2xl shadow-primary/5">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary via-cyan-400 to-primary" />
                <CardContent className="pt-8 pb-8 px-6 sm:px-10">
                    <form onSubmit={handleAsk} className="relative flex items-center">
                        <Search className="absolute left-4 h-5 w-5 text-muted-foreground" />
                        <Input
                            value={question}
                            onChange={(e) => setQuestion(e.target.value)}
                            placeholder="e.g. What is the average score by topic?"
                            className="pl-12 pr-32 h-14 text-lg bg-black/40 border-white/20 focus:border-primary/50 focus:ring-primary/20 rounded-full"
                        />
                        <Button
                            type="submit"
                            disabled={isAsking || !question.trim()}
                            className="absolute right-2 h-10 rounded-full w-[110px] bg-primary hover:bg-primary/90 text-white shadow-lg shadow-primary/25"
                        >
                            {isAsking ? <Loader2 className="h-5 w-5 animate-spin" /> : "Ask AI"}
                        </Button>
                    </form>

                    <div className="mt-6">
                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 ml-2">Suggested Queries</p>
                        <div className="flex flex-wrap gap-2">
                            {SUGGESTED_QUESTIONS.map((q, i) => (
                                <button
                                    key={i}
                                    type="button"
                                    onClick={() => handleAsk(undefined, q)}
                                    className="text-sm px-4 py-2 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 hover:border-primary/30 transition-all flex items-center gap-2 group"
                                >
                                    {q}
                                    <ChevronRight className="h-3 w-3 opacity-0 -ml-2 group-hover:opacity-100 group-hover:block transition-all text-primary" />
                                </button>
                            ))}
                        </div>
                    </div>
                </CardContent>
            </Card>

            <AnimatePresence mode="wait">
                {result && (
                    <motion.div
                        key="result"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ duration: 0.4 }}
                        className="space-y-6"
                    >
                        {result.error ? (
                            <Card className="border-destructive/20 bg-destructive/5">
                                <CardContent className="pt-6 flex items-start gap-4">
                                    <AlertCircle className="h-6 w-6 text-destructive shrink-0 mt-0.5" />
                                    <div>
                                        <h3 className="text-lg font-semibold text-destructive mb-1">Query Failed</h3>
                                        <p className="text-muted-foreground">{result.error}</p>
                                    </div>
                                </CardContent>
                            </Card>
                        ) : (
                            <>
                                <Card className="glass-panel border-white/5">
                                    <CardHeader className="flex flex-row items-center justify-between pb-2 bg-black/20 rounded-t-xl">
                                        <div className="flex items-center gap-2 text-muted-foreground text-sm font-mono">
                                            <Database className="h-4 w-4" />
                                            Generated SQL
                                        </div>
                                    </CardHeader>
                                    <CardContent className="pt-4 font-mono text-cyan-200 text-sm overflow-x-auto whitespace-pre-wrap">
                                        {result.sql}
                                    </CardContent>
                                </Card>

                                <Card className="glass-panel border-white/5 overflow-hidden">
                                    <CardHeader>
                                        <CardTitle className="text-xl">Query Results</CardTitle>
                                        <CardDescription>
                                            {result.results?.length || 0} rows returned
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent className="p-0">
                                        {!result.results || result.results.length === 0 ? (
                                            <div className="p-8 text-center text-muted-foreground bg-black/20">
                                                No results found for this query.
                                            </div>
                                        ) : (
                                            <div className="overflow-x-auto">
                                                <Table>
                                                    <TableHeader>
                                                        <TableRow className="bg-black/40 border-b border-white/10 hover:bg-transparent">
                                                            {Object.keys(result.results[0]).map((key) => (
                                                                <TableHead key={key} className="font-semibold text-primary-100 capitalize">
                                                                    {key.replace(/_/g, ' ')}
                                                                </TableHead>
                                                            ))}
                                                        </TableRow>
                                                    </TableHeader>
                                                    <TableBody>
                                                        {result.results.map((row: any, i: number) => (
                                                            <TableRow key={i} className="border-b border-white/5 hover:bg-white/5">
                                                                {Object.values(row).map((val: any, j: number) => (
                                                                    <TableCell key={j} className="text-muted-foreground">
                                                                        {val === null ? <span className="text-white/20 italic">null</span> : String(val)}
                                                                    </TableCell>
                                                                ))}
                                                            </TableRow>
                                                        ))}
                                                    </TableBody>
                                                </Table>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            </>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
