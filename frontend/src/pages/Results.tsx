import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLocation } from 'react-router-dom';
import { Award, Clock, FileText, CheckCircle2, ChevronDown, ChevronUp, Loader2, MessageSquare } from 'lucide-react';
import { submissionAPI } from '../lib/api';
import type { Submission } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent } from '../components/ui/card';

export function Results() {
    const { user } = useAuth();
    const location = useLocation();
    const successMessage = location.state?.successMessage;

    const [submissions, setSubmissions] = useState<Submission[]>([]);
    const [loading, setLoading] = useState(true);
    const [expandedId, setExpandedId] = useState<number | null>(null);

    useEffect(() => {
        const fetchResults = async () => {
            if (!user) return;
            try {
                const data = await submissionAPI.getStudentSubmissions(user.id);
                setSubmissions(data || []);
            } catch (err) {
                console.error("Failed to load results", err);
            } finally {
                setLoading(false);
            }
        };

        fetchResults();
    }, [user]);

    const toggleExpand = (id: number) => {
        setExpandedId(expandedId === id ? null : id);
    };

    if (loading) {
        return (
            <div className="flex h-[60vh] justify-center items-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <AnimatePresence>
                {successMessage && (
                    <motion.div
                        initial={{ opacity: 0, y: -20, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                        className="bg-green-500/10 border border-green-500/20 text-green-400 p-4 rounded-xl flex items-center gap-3 shadow-lg shadow-green-500/5"
                    >
                        <CheckCircle2 className="h-6 w-6" />
                        <span className="font-medium">{successMessage}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            <div>
                <h1 className="text-3xl font-bold tracking-tight">My Results</h1>
                <p className="text-muted-foreground mt-2">View your past submissions and AI feedback.</p>
            </div>

            {submissions.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground glass-panel rounded-xl border-dashed">
                    You haven't submitted any exams yet.
                </div>
            ) : (
                <div className="space-y-4">
                    {submissions.map((sub, i) => (
                        <motion.div
                            key={sub.submission_id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.1 }}
                        >
                            <Card className={`glass-panel border-white/5 overflow-hidden transition-all ${expandedId === sub.submission_id ? 'ring-1 ring-primary/50' : 'hover:border-white/20'}`}>
                                <div
                                    className="flex flex-col sm:flex-row justify-between items-start sm:items-center p-6 cursor-pointer"
                                    onClick={() => toggleExpand(sub.submission_id)}
                                >
                                    <div className="space-y-1">
                                        <h3 className="text-xl font-semibold flex items-center gap-2 group-hover:text-primary transition-colors">
                                            <FileText className="h-5 w-5 text-cyan-400" />
                                            {sub.exam_topic || `Exam #${sub.exam_id}`}
                                        </h3>
                                        <p className="text-sm text-muted-foreground flex items-center gap-2">
                                            <Clock className="h-4 w-4" /> Submitted on {new Date(sub.submitted_at).toLocaleDateString()}
                                        </p>
                                    </div>

                                    <div className="flex items-center gap-4 mt-4 sm:mt-0">
                                        {sub.numerical_score !== null ? (
                                            <div className={`px-4 py-2 rounded-full font-bold flex items-center gap-2 ${sub.numerical_score >= 80 ? 'bg-green-500/20 text-green-400' :
                                                sub.numerical_score >= 60 ? 'bg-yellow-500/20 text-yellow-400' :
                                                    'bg-destructive/20 text-destructive'
                                                }`}>
                                                <Award className="h-5 w-5" />
                                                {sub.numerical_score}%
                                            </div>
                                        ) : (
                                            <div className="px-4 py-2 rounded-full font-semibold bg-white/5 text-muted-foreground border border-white/10">
                                                Pending Grade
                                            </div>
                                        )}
                                        {expandedId === sub.submission_id ? <ChevronUp className="text-muted-foreground" /> : <ChevronDown className="text-muted-foreground" />}
                                    </div>
                                </div>

                                <AnimatePresence>
                                    {expandedId === sub.submission_id && (
                                        <motion.div
                                            initial={{ opacity: 0, height: 0 }}
                                            animate={{ opacity: 1, height: 'auto' }}
                                            exit={{ opacity: 0, height: 0 }}
                                            className="border-t border-white/5 bg-black/20"
                                        >
                                            <CardContent className="p-6 space-y-6">
                                                {/* Instructor Note */}
                                                {sub.grader_note && (
                                                    <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
                                                        <h4 className="flex items-center gap-2 text-sm font-semibold text-primary mb-2 uppercase tracking-wide">
                                                            <MessageSquare className="h-4 w-4" /> Instructor Note
                                                        </h4>
                                                        <p className="text-sm text-primary-100">{sub.grader_note}</p>
                                                    </div>
                                                )}

                                                {/* AI Feedback */}
                                                {sub.ai_feedback && (
                                                    <div className="space-y-2">
                                                        <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide border-b border-white/5 pb-2">
                                                            AI Feedback Report
                                                        </h4>
                                                        <div className="prose prose-invert prose-sm max-w-none text-muted-foreground whitespace-pre-wrap pt-2">
                                                            {sub.ai_feedback}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Answers Raw Data Preview */}
                                                <div className="space-y-2">
                                                    <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide border-b border-white/5 pb-2">
                                                        Your Raw Answers
                                                    </h4>
                                                    <pre className="text-xs bg-black/40 p-4 rounded-md overflow-x-auto text-cyan-100 border border-white/5">
                                                        {typeof sub.student_answers === 'string' && sub.student_answers.startsWith('{')
                                                            ? JSON.stringify(JSON.parse(sub.student_answers), null, 2)
                                                            : sub.student_answers}
                                                    </pre>
                                                </div>
                                            </CardContent>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </Card>
                        </motion.div>
                    ))}
                </div>
            )}
        </div>
    );
}
