import { useEffect, useRef } from 'react';

interface Particle {
    x: number;
    y: number;
    size: number;
    speed: number;
    opacity: number;
    twinkleSpeed: number;
    twinklePhase: number;
}

const SparkleBackground = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let animationId: number;
        let particles: Particle[] = [];

        const resize = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };

        const createParticles = () => {
            const count = Math.floor((canvas.width * canvas.height) / 12000);
            particles = [];
            for (let i = 0; i < count; i++) {
                particles.push({
                    x: Math.random() * canvas.width,
                    y: Math.random() * canvas.height,
                    size: Math.random() * 1.6 + 0.3,
                    speed: Math.random() * 0.15 + 0.04,
                    opacity: Math.random() * 0.55 + 0.1,
                    twinkleSpeed: Math.random() * 0.008 + 0.003,
                    twinklePhase: Math.random() * Math.PI * 2,
                });
            }
        };

        const animate = (time: number) => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            for (const p of particles) {
                p.y -= p.speed;
                if (p.y < -5) {
                    p.y = canvas.height + 5;
                    p.x = Math.random() * canvas.width;
                }

                const twinkle = Math.sin(time * p.twinkleSpeed + p.twinklePhase);
                const alpha = p.opacity * (0.5 + twinkle * 0.5);

                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(255, 255, 255, ${Math.max(0, alpha)})`;
                ctx.fill();
            }

            animationId = requestAnimationFrame(animate);
        };

        resize();
        createParticles();
        animationId = requestAnimationFrame(animate);

        const handleResize = () => {
            resize();
            createParticles();
        };

        window.addEventListener('resize', handleResize);

        return () => {
            cancelAnimationFrame(animationId);
            window.removeEventListener('resize', handleResize);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className="fixed inset-0 z-0 pointer-events-none"
            style={{ background: '#000000' }}
        />
    );
};

export default SparkleBackground;
