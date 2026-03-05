import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, FileText, Loader2, Sparkles, CheckCircle2, BrainCircuit, AlertCircle, Send } from 'lucide-react';
import { ragAPI, examAPI } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card';

export function ExamGenerator() {
    const { user } = useAuth();
    const fileInputRef = useRef<HTMLInputElement>(null);

    // PDF Upload State
    const [pdfs, setPdfs] = useState<string[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

    // Generation State
    const [topic, setTopic] = useState('');
    const [difficulty, setDifficulty] = useState('Intermediate');
    const [mcqCount, setMcqCount] = useState(5);
    const [essayCount, setEssayCount] = useState(2);
    const [isGenerating, setIsGenerating] = useState(false);

    // Generated Exam State
    const [generatedExam, setGeneratedExam] = useState<{ content: string, sources: string[] } | null>(null);
    const [savedExamId, setSavedExamId] = useState<number | null>(null);
    const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

    const fetchPdfs = async () => {
        try {
            const res = await ragAPI.getPdfs();
            setPdfs(res.pdfs || []);
        } catch (err) {
            console.error("Failed to fetch PDFs", err);
        }
    };

    useEffect(() => {
        fetchPdfs();
    }, []);

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0 || !user) return;

        setIsUploading(true);
        setUploadMessage(null);

        try {
            const fileArray = Array.from(files);
            const res = await ragAPI.uploadPdfs(user.id, fileArray);

            let message = `Successfully uploaded ${res.added.length} files. `;
            if (res.skipped?.length > 0) message += `Skipped ${res.skipped.length} existing.`;

            setUploadMessage({ type: 'success', text: message });
            fetchPdfs();
        } catch (err: any) {
            console.error(err);
            setUploadMessage({ type: 'error', text: err.response?.data?.detail || "Failed to upload PDFs" });
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleGenerate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!topic) return;

        setIsGenerating(true);
        setStatusMessage(null);
        setGeneratedExam(null);
        setSavedExamId(null);

        try {
            const res = await ragAPI.generate({
                topic,
                difficulty,
                mcq_count: mcqCount,
                essay_count: essayCount
            });
            setGeneratedExam(res);
            setStatusMessage({ type: 'success', text: 'Exam generated successfully!' });
        } catch (err: any) {
            setStatusMessage({ type: 'error', text: err.response?.data?.detail || "Failed to generate exam" });
        } finally {
            setIsGenerating(false);
        }
    };

    const handleSaveDraft = async () => {
        if (!generatedExam || !user) return;

        try {
            const res = await examAPI.create({
                instructor_id: user.id,
                topic,
                difficulty,
                content: generatedExam.content,
                status: "draft",
                source_refs: generatedExam.sources
            });
            setSavedExamId(res.id);
            setStatusMessage({ type: 'success', text: `Exam saved as draft (ID: ${res.id})` });
        } catch (err: any) {
            setStatusMessage({ type: 'error', text: "Failed to save exam" });
        }
    };

    const handlePublish = async () => {
        if (!savedExamId || !user) return;

        try {
            await examAPI.update(savedExamId, {
                instructor_id: user.id,
                status: "published"
            });
            setStatusMessage({ type: 'success', text: `Exam ${savedExamId} Published successfully!` });
        } catch (err: any) {
            setStatusMessage({ type: 'error', text: "Failed to publish exam" });
        }
    };

    return (
        <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Exam Generator</h1>
                    <p className="text-muted-foreground">Upload knowledge base PDFs and generate AI-powered exams.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Left Column: PDF Manager */}
                <div className="md:col-span-1 space-y-6">
                    <Card className="glass-panel border-white/5">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <FileText className="h-5 w-5 text-cyan-400" />
                                Knowledge Base (PDFs)
                            </CardTitle>
                            <CardDescription>Upload course materials for the AI to reference.</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div
                                onClick={() => fileInputRef.current?.click()}
                                className="border-2 border-dashed border-white/10 rounded-xl p-6 flex flex-col items-center justify-center gap-2 text-muted-foreground hover:bg-white/5 hover:border-primary/50 transition-colors cursor-pointer"
                            >
                                {isUploading ? (
                                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                                ) : (
                                    <Upload className="h-8 w-8 text-muted-foreground" />
                                )}
                                <span className="text-sm font-medium">Click to upload PDFs</span>
                                <span className="text-xs">Max 20MB per file</span>
                                <input
                                    type="file"
                                    ref={fileInputRef}
                                    onChange={handleFileUpload}
                                    className="hidden"
                                    multiple
                                    accept=".pdf"
                                />
                            </div>

                            {uploadMessage && (
                                <div className={`text - sm p - 3 rounded - md flex items - start gap - 2 ${uploadMessage.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-destructive/10 text-destructive border border-destructive/20'} `}>
                                    {uploadMessage.type === 'success' ? <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" /> : <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />}
                                    <span>{uploadMessage.text}</span>
                                </div>
                            )}

                            <div className="space-y-2">
                                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Available Documents</Label>
                                <div className="bg-black/30 rounded-lg p-3 max-h-48 overflow-y-auto space-y-2 border border-white/5">
                                    {pdfs.length === 0 ? (
                                        <div className="text-sm text-center text-muted-foreground py-4">No PDFs uploaded yet.</div>
                                    ) : (
                                        pdfs.map((pdf, i) => (
                                            <div key={i} className="flex items-center gap-2 text-sm bg-white/5 p-2 rounded-md transition-colors hover:bg-white/10">
                                                <FileText className="h-4 w-4 text-cyan-400 shrink-0" />
                                                <span className="truncate" title={pdf}>{pdf}</span>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Right Column: Generator Form */}
                <div className="md:col-span-2 space-y-6">
                    <Card className="glass-panel border-white/5 relative overflow-hidden">
                        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/10 rounded-full blur-[80px] -z-10 pointer-events-none translate-x-1/2 -translate-y-1/2" />

                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Sparkles className="h-5 w-5 text-primary" />
                                Configure Exam Parameters
                            </CardTitle>
                            <CardDescription>Tell the AI what kind of exam to generate.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <form onSubmit={handleGenerate} className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="topic">Main Topic / Subject</Label>
                                    <Input
                                        id="topic"
                                        placeholder="e.g. History of the Roman Empire"
                                        value={topic}
                                        onChange={(e) => setTopic(e.target.value)}
                                        required
                                        className="bg-black/50 border-white/10 focus:border-primary/50"
                                    />
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="difficulty">Difficulty</Label>
                                        <select
                                            id="difficulty"
                                            value={difficulty}
                                            onChange={(e) => setDifficulty(e.target.value)}
                                            className="flex h-10 w-full rounded-md border border-input bg-black/50 border-white/10 px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                        >
                                            <option value="Beginner">Beginner</option>
                                            <option value="Intermediate">Intermediate</option>
                                            <option value="Advanced">Advanced</option>
                                            <option value="Expert">Expert</option>
                                        </select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="mcqCount">MCQ Count (1-20)</Label>
                                        <Input
                                            id="mcqCount"
                                            type="number"
                                            min={1} max={20}
                                            value={mcqCount}
                                            onChange={(e) => setMcqCount(parseInt(e.target.value))}
                                            className="bg-black/50 border-white/10 focus:border-primary/50"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="essayCount">Essay Count (0-10)</Label>
                                        <Input
                                            id="essayCount"
                                            type="number"
                                            min={0} max={10}
                                            value={essayCount}
                                            onChange={(e) => setEssayCount(parseInt(e.target.value))}
                                            className="bg-black/50 border-white/10 focus:border-primary/50"
                                        />
                                    </div>
                                </div>

                                <Button
                                    type="submit"
                                    disabled={isGenerating || !topic}
                                    className="w-full mt-6 bg-primary hover:bg-primary/90 text-white shadow-lg shadow-primary/25 transition-all"
                                >
                                    {isGenerating ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Synthesizing Knowledge Base...
                                        </>
                                    ) : (
                                        <>
                                            <BrainCircuit className="mr-2 h-4 w-4" />
                                            Generate Exam using AI
                                        </>
                                    )}
                                </Button>
                            </form>

                            <AnimatePresence>
                                {statusMessage && (
                                    <motion.div
                                        initial={{ opacity: 0, height: 0 }}
                                        animate={{ opacity: 1, height: 'auto' }}
                                        exit={{ opacity: 0, height: 0 }}
                                        className={`mt - 4 text - sm p - 4 rounded - lg flex items - start gap - 2 ${statusMessage.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-destructive/10 text-destructive border border-destructive/20'
                                            } `}
                                    >
                                        {statusMessage.type === 'success' ? <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" /> : <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />}
                                        <span>{statusMessage.text}</span>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                        </CardContent>
                    </Card>

                    {/* Generated Content Preview & Actions */}
                    <AnimatePresence>
                        {generatedExam && (
                            <motion.div
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ duration: 0.4 }}
                            >
                                <Card className="glass-panel border-primary/20 bg-primary/5">
                                    <CardHeader>
                                        <CardTitle className="flex justify-between items-center">
                                            <span>Exam Generated Successfully</span>
                                            <span className="text-xs font-normal bg-black/40 px-2 py-1 rounded-full text-muted-foreground">
                                                {generatedExam.sources.length} sources referenced
                                            </span>
                                        </CardTitle>
                                        <CardDescription>Review the exam JSON below or proceed to save it.</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="bg-black/60 p-4 rounded-lg max-h-64 overflow-y-auto border border-white/10">
                                            <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono">
                                                {generatedExam.content}
                                            </pre>
                                        </div>
                                    </CardContent>
                                    <CardFooter className="flex flex-col sm:flex-row gap-4 border-t border-white/5 pt-6">
                                        {!savedExamId ? (
                                            <Button onClick={handleSaveDraft} className="w-full sm:w-auto bg-white/10 hover:bg-white/20 text-white">
                                                <Send className="mr-2 h-4 w-4" />
                                                Save as Draft
                                            </Button>
                                        ) : (
                                            <Button onClick={handlePublish} className="w-full sm:w-auto bg-green-500 hover:bg-green-600 text-white shadow-lg shadow-green-500/20">
                                                <CheckCircle2 className="mr-2 h-4 w-4" />
                                                Publish for Students
                                            </Button>
                                        )}
                                    </CardFooter>
                                </Card>
                            </motion.div>
                        )}
                    </AnimatePresence>

                </div>
            </div>
        </div>
    );
}
