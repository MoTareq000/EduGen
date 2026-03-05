import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, RotateCcw, AlertCircle, Loader2, ShieldAlert, ShieldCheck, Clock3 } from 'lucide-react';
import { instructorAPI, proctorAPI, submissionAPI } from '../lib/api';
import type { ProctorAlert, ProctorSessionSummary, Submission } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';

export function GradingHub() {
    const { user } = useAuth();
    const [submissions, setSubmissions] = useState<Submission[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [proctorError, setProctorError] = useState<string | null>(null);
    const [proctorSessions, setProctorSessions] = useState<ProctorSessionSummary[]>([]);
    const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
    const [selectedSessionAlerts, setSelectedSessionAlerts] = useState<ProctorAlert[]>([]);
    const [isLoadingAlerts, setIsLoadingAlerts] = useState(false);

    // Grading / Override State
    const [isGrading, setIsGrading] = useState<number | null>(null);
    const [overrideScores, setOverrideScores] = useState<{ [key: number]: string }>({});
    const [overrideNotes, setOverrideNotes] = useState<{ [key: number]: string }>({});

    const fetchSubmissions = async () => {
        if (!user) return;
        setIsLoading(true);
        try {
            const data = await instructorAPI.getSubmissions(user.id);
            setSubmissions(data || []);
        } catch (err: any) {
            setError(err.response?.data?.detail || "Failed to load submissions");
        } finally {
            setIsLoading(false);
        }
    };

    const fetchProctorSessions = async () => {
        if (!user) return;
        try {
            const data = await proctorAPI.getInstructorSessions(user.id, 100);
            const sessions = data?.sessions || [];
            setProctorSessions(sessions);
            if (!selectedSessionId && sessions.length > 0) {
                setSelectedSessionId(sessions[0].id);
            }
        } catch (err: any) {
            setProctorError(err.response?.data?.detail || 'Failed to load proctor sessions');
        }
    };

    const fetchSessionAlerts = async (sessionId: string) => {
        setIsLoadingAlerts(true);
        try {
            const data = await proctorAPI.getSessionAlerts(sessionId);
            setSelectedSessionAlerts(data?.alerts || []);
        } catch (err: any) {
            setProctorError(err.response?.data?.detail || 'Failed to load session alerts');
        } finally {
            setIsLoadingAlerts(false);
        }
    };

    useEffect(() => {
        fetchSubmissions();
        fetchProctorSessions();
        const poll = window.setInterval(fetchProctorSessions, 5000);
        return () => window.clearInterval(poll);
    }, [user]);

    useEffect(() => {
        if (!selectedSessionId) {
            setSelectedSessionAlerts([]);
            return;
        }
        fetchSessionAlerts(selectedSessionId);
        const poll = window.setInterval(() => fetchSessionAlerts(selectedSessionId), 5000);
        return () => window.clearInterval(poll);
    }, [selectedSessionId]);

    const handleGrade = async (submissionId: number) => {
        if (!user) return;
        setIsGrading(submissionId);
        try {
            await submissionAPI.grade({ submission_id: submissionId, instructor_id: user.id });
            await fetchSubmissions(); // Refresh
        } catch (err: any) {
            alert(err.response?.data?.detail || "Failed to grade submission");
        } finally {
            setIsGrading(null);
        }
    };

    const handleOverride = async (submissionId: number) => {
        if (!user) return;
        const scoreStr = overrideScores[submissionId];
        if (!scoreStr) return;

        const score = parseInt(scoreStr);
        if (isNaN(score) || score < 0 || score > 100) {
            alert("Score must be between 0 and 100");
            return;
        }

        try {
            await submissionAPI.override(submissionId, {
                instructor_id: user.id,
                score,
                note: overrideNotes[submissionId]
            });
            await fetchSubmissions(); // Refresh

            // Clear inputs
            setOverrideScores(prev => ({ ...prev, [submissionId]: '' }));
            setOverrideNotes(prev => ({ ...prev, [submissionId]: '' }));
        } catch (err: any) {
            alert(err.response?.data?.detail || "Failed to override score");
        }
    };

    if (isLoading) {
        return (
            <div className="flex justify-center items-center h-[60vh]">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Grading Hub</h1>
                <p className="text-muted-foreground">Review and grade all student submissions across your exams.</p>
            </div>

            {error && (
                <div className="bg-destructive/10 text-destructive p-4 rounded-md flex items-center gap-2 border border-destructive/20">
                    <AlertCircle className="h-5 w-5" />
                    {error}
                </div>
            )}
            {proctorError && (
                <div className="bg-destructive/10 text-destructive p-4 rounded-md flex items-center gap-2 border border-destructive/20">
                    <AlertCircle className="h-5 w-5" />
                    {proctorError}
                </div>
            )}

            <Card className="glass-panel border-white/5">
                <CardHeader>
                    <CardTitle>Live Proctor Feed</CardTitle>
                    <CardDescription>Session counters and alert logs for your students.</CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="rounded-lg border border-white/10 overflow-hidden">
                        <div className="px-3 py-2 text-xs uppercase tracking-wider text-muted-foreground border-b border-white/10">Sessions</div>
                        {proctorSessions.length === 0 ? (
                            <div className="px-3 py-4 text-sm text-muted-foreground">No proctor sessions yet.</div>
                        ) : (
                            <div className="max-h-72 overflow-y-auto">
                                {proctorSessions.map((session) => (
                                    <button
                                        key={session.id}
                                        className={`w-full text-left px-3 py-3 border-b border-white/5 hover:bg-white/5 transition-colors ${selectedSessionId === session.id ? 'bg-white/10' : ''}`}
                                        onClick={() => setSelectedSessionId(session.id)}
                                    >
                                        <div className="flex items-center justify-between gap-2">
                                            <div className="font-medium text-sm">{session.student_name} - {session.exam_title}</div>
                                            <div className={`text-xs px-2 py-0.5 rounded-full ${session.ended_at ? 'bg-white/10 text-muted-foreground' : 'bg-green-500/20 text-green-400'}`}>
                                                {session.ended_at ? 'Ended' : 'Live'}
                                            </div>
                                        </div>
                                        <div className="mt-1 text-xs text-muted-foreground flex gap-3 flex-wrap">
                                            <span>Alerts: {session.total_alerts}</span>
                                            <span>High: {session.high_alerts}</span>
                                            <span>Start: {new Date(session.started_at).toLocaleTimeString()}</span>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="rounded-lg border border-white/10 overflow-hidden">
                        <div className="px-3 py-2 text-xs uppercase tracking-wider text-muted-foreground border-b border-white/10">Alert Log</div>
                        {!selectedSessionId ? (
                            <div className="px-3 py-4 text-sm text-muted-foreground">Select a session to view details.</div>
                        ) : (
                            <>
                                {(() => {
                                    const selected = proctorSessions.find((s) => s.id === selectedSessionId);
                                    if (!selected) return null;
                                    return (
                                        <div className="px-3 py-3 border-b border-white/10 grid grid-cols-3 gap-2 text-xs">
                                            <div className="rounded bg-black/30 p-2">
                                                <p className="text-muted-foreground">Total Alerts</p>
                                                <p className="font-bold text-cyan-300">{selected.total_alerts}</p>
                                            </div>
                                            <div className="rounded bg-black/30 p-2">
                                                <p className="text-muted-foreground">High Alerts</p>
                                                <p className="font-bold text-cyan-300">{selected.high_alerts}</p>
                                            </div>
                                            <div className="rounded bg-black/30 p-2">
                                                <p className="text-muted-foreground">Status</p>
                                                <p className="font-bold text-cyan-300">{selected.invalidated ? 'Invalidated' : selected.ended_at ? 'Ended' : 'Live'}</p>
                                            </div>
                                        </div>
                                    );
                                })()}
                                {isLoadingAlerts ? (
                                    <div className="px-3 py-4 text-sm text-muted-foreground flex items-center gap-2">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Loading alerts...
                                    </div>
                                ) : selectedSessionAlerts.length === 0 ? (
                                    <div className="px-3 py-4 text-sm text-muted-foreground">No alerts logged for this session.</div>
                                ) : (
                                    <div className="max-h-72 overflow-y-auto">
                                        {selectedSessionAlerts.slice().reverse().map((alert) => (
                                            <div key={alert.id} className="px-3 py-2 border-b border-white/5 text-xs flex items-center gap-3">
                                                <span className="font-mono text-muted-foreground w-20 flex items-center gap-1">
                                                    <Clock3 className="h-3 w-3" />
                                                    {new Date(alert.at).toLocaleTimeString()}
                                                </span>
                                                <span className={`inline-block h-3 w-3 rounded-full ${alert.severity === 'high'
                                                    ? 'bg-red-400'
                                                    : alert.severity === 'medium'
                                                        ? 'bg-yellow-400'
                                                        : 'bg-green-400'
                                                    }`} />
                                                <span className={`${alert.severity === 'high' ? 'text-red-300' : alert.severity === 'medium' ? 'text-yellow-200' : 'text-green-300'}`}>
                                                    {alert.message}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </CardContent>
            </Card>

            <Card className="glass-panel border-white/5">
                <CardHeader>
                    <CardTitle>Pending & Completed Grades</CardTitle>
                    <CardDescription>Use AI to auto-grade or manually override scores.</CardDescription>
                </CardHeader>
                <CardContent>
                    {submissions.length === 0 ? (
                        <div className="text-center py-12 text-muted-foreground border border-dashed border-white/10 rounded-xl bg-white/5">
                            No submissions found for your exams yet.
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow className="border-white/10 hover:bg-transparent">
                                    <TableHead>Student</TableHead>
                                    <TableHead>Exam Topic</TableHead>
                                    <TableHead>Submitted At</TableHead>
                                    <TableHead className="text-center">Score</TableHead>
                                    <TableHead>Status / Action</TableHead>
                                    <TableHead>Proctoring</TableHead>
                                    <TableHead>Manual Override</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {submissions.map((sub, i) => (
                                    <motion.tr
                                        key={sub.submission_id}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: i * 0.05 }}
                                        className="border-white/5 hover:bg-white/5"
                                    >
                                        <TableCell className="font-medium text-cyan-100">{sub.student_username || `ID: ${sub.student_id}`}</TableCell>
                                        <TableCell className="truncate max-w-[150px]" title={sub.exam_topic}>{sub.exam_topic}</TableCell>
                                        <TableCell className="text-muted-foreground">{new Date(sub.submitted_at).toLocaleDateString()}</TableCell>

                                        <TableCell className="text-center">
                                            {sub.numerical_score !== null ? (
                                                <span className={`inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-xs font-medium ${sub.numerical_score >= 80 ? 'bg-green-500/20 text-green-400' : sub.numerical_score >= 60 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-destructive/20 text-destructive'}`}>
                                                    {sub.numerical_score}%
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground text-xs italic">Ungraded</span>
                                            )}
                                        </TableCell>

                                        <TableCell>
                                            {sub.numerical_score === null ? (
                                                <Button
                                                    size="sm"
                                                    onClick={() => handleGrade(sub.submission_id)}
                                                    disabled={isGrading === sub.submission_id}
                                                    className="w-full bg-primary/20 text-primary hover:bg-primary/30 border border-primary/30"
                                                >
                                                    {isGrading === sub.submission_id ? <Loader2 className="h-3 w-3 animate-spin" /> : 'AI Grade'}
                                                </Button>
                                            ) : (
                                                <div className="flex items-center gap-1 text-green-400 text-sm">
                                                    <CheckCircle2 className="h-4 w-4" /> Graded
                                                </div>
                                            )}
                                        </TableCell>

                                        <TableCell>
                                            {sub.proctor_session_id ? (
                                                <div className="space-y-1 text-xs">
                                                    <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${sub.proctor_invalidated ? 'bg-destructive/20 text-destructive' : 'bg-green-500/20 text-green-400'}`}>
                                                        {sub.proctor_invalidated ? <ShieldAlert className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                                                        {sub.proctor_invalidated ? 'Invalidated' : 'Valid'}
                                                    </div>
                                                    <div className="text-muted-foreground">
                                                        Focus: {sub.proctor_focus_score_final ?? 'N/A'}%
                                                    </div>
                                                    <div className="text-muted-foreground">
                                                        Alerts: {sub.proctor_total_alerts ?? 0} ({sub.proctor_high_alerts ?? 0} high)
                                                    </div>
                                                </div>
                                            ) : (
                                                <span className="text-muted-foreground text-xs italic">No proctor data</span>
                                            )}
                                        </TableCell>

                                        <TableCell>
                                            <div className="flex items-center gap-2">
                                                <Input
                                                    placeholder="Score"
                                                    className="w-16 h-8 text-xs bg-black/50 border-white/10"
                                                    value={overrideScores[sub.submission_id] || ''}
                                                    onChange={(e) => setOverrideScores(prev => ({ ...prev, [sub.submission_id]: e.target.value }))}
                                                />
                                                <Input
                                                    placeholder="Note"
                                                    className="w-24 h-8 text-xs bg-black/50 border-white/10"
                                                    value={overrideNotes[sub.submission_id] || ''}
                                                    onChange={(e) => setOverrideNotes(prev => ({ ...prev, [sub.submission_id]: e.target.value }))}
                                                />
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    className="h-8 w-8 text-muted-foreground hover:text-cyan-400"
                                                    onClick={() => handleOverride(sub.submission_id)}
                                                    disabled={!overrideScores[sub.submission_id]}
                                                >
                                                    <RotateCcw className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </TableCell>
                                    </motion.tr>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
