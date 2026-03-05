import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { FileText, Clock, PlayCircle, Loader2, Award } from 'lucide-react';
import { examAPI, submissionAPI } from '../lib/api';
import type { ExamSummary } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '../components/ui/card';

export function MyExams() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [exams, setExams] = useState<(ExamSummary & { has_submitted?: boolean })[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchExams = async () => {
            if (!user) return;
            try {
                const publishedExams = await examAPI.getAll({ status: 'published' });

                // For each exam, check if student already submitted
                const examsWithStatus = await Promise.all(
                    publishedExams.map(async (exam) => {
                        try {
                            const subcheck = await submissionAPI.checkExists(exam.id, user.id);
                            return { ...exam, has_submitted: subcheck.exists };
                        } catch (err) {
                            return { ...exam, has_submitted: false };
                        }
                    })
                );

                setExams(examsWithStatus);
            } catch (err) {
                console.error("Failed to load exams", err);
            } finally {
                setLoading(false);
            }
        };

        fetchExams();
    }, [user]);

    if (loading) {
        return (
            <div className="flex h-[60vh] justify-center items-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">My Exams</h1>
                <p className="text-muted-foreground mt-2">Available assessments and your completed tests.</p>
            </div>

            {exams.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground glass-panel rounded-xl border-dashed">
                    No published exams are currently available. Check back later!
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {exams.map((exam, i) => {
                        const isClosed = exam.due_at ? new Date(exam.due_at) < new Date() : false;

                        return (
                            <motion.div
                                key={exam.id}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: i * 0.1 }}
                                whileHover={{ y: -5 }}
                            >
                                <Card className="h-full flex flex-col glass-panel border-white/5 relative overflow-hidden group">
                                    <div className={`absolute top-0 left-0 w-full h-1 ${exam.has_submitted ? 'bg-green-500' : isClosed ? 'bg-muted' : 'bg-primary'}`} />

                                    <CardHeader>
                                        <div className="flex justify-between items-start mb-2">
                                            <span className="text-xs font-semibold px-2 py-1 rounded-full bg-black/40 border border-white/10 uppercase tracking-wider text-muted-foreground">
                                                {exam.difficulty}
                                            </span>
                                            {exam.has_submitted ? (
                                                <span className="flex items-center gap-1 text-xs font-medium text-green-400 bg-green-500/10 px-2 py-1 rounded-full">
                                                    <CheckCircle2 className="h-3 w-3" /> Completed
                                                </span>
                                            ) : isClosed ? (
                                                <span className="text-xs font-medium text-muted-foreground bg-white/5 px-2 py-1 rounded-full border border-white/10">
                                                    Closed
                                                </span>
                                            ) : null}
                                        </div>
                                        <CardTitle className="text-xl line-clamp-2 leading-tight group-hover:text-primary transition-colors">
                                            {exam.topic}
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent className="flex-1 space-y-4">
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <Clock className="h-4 w-4" />
                                            <span>{exam.due_at ? `Due: ${new Date(exam.due_at).toLocaleDateString()}` : 'No due date'}</span>
                                        </div>
                                        {exam.rubric && (
                                            <div className="flex items-start gap-2 text-sm text-muted-foreground mt-2 bg-black/20 p-2 rounded-md">
                                                <FileText className="h-4 w-4 shrink-0 mt-0.5" />
                                                <span className="line-clamp-2 text-xs italic opacity-80">{exam.rubric}</span>
                                            </div>
                                        )}
                                    </CardContent>
                                    <CardFooter className="pt-4 border-t border-white/5">
                                        {exam.has_submitted ? (
                                            <Button
                                                variant="secondary"
                                                className="w-full bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/20"
                                                onClick={() => navigate('/results')}
                                            >
                                                <Award className="mr-2 h-4 w-4" /> View Results
                                            </Button>
                                        ) : isClosed ? (
                                            <Button variant="outline" className="w-full" disabled>
                                                Exam Closed
                                            </Button>
                                        ) : (
                                            <Button
                                                className="w-full bg-primary hover:bg-primary/90 text-white shadow-lg shadow-primary/20"
                                                onClick={() => navigate(`/take-exam/${exam.id}`)}
                                            >
                                                <PlayCircle className="mr-2 h-4 w-4" /> Start Exam
                                            </Button>
                                        )}
                                    </CardFooter>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

const CheckCircle2 = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" /><path d="m9 12 2 2 4-4" /></svg>
);
