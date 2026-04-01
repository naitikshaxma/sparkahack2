const SparkleBackground = () => {
  const dots = [
    { top: "10%", left: "6%", size: 7, opacity: 0.45, delay: "0s", duration: "16s" },
    { top: "18%", left: "78%", size: 5, opacity: 0.4, delay: "1s", duration: "18s" },
    { top: "28%", left: "42%", size: 4, opacity: 0.35, delay: "2s", duration: "20s" },
    { top: "40%", left: "12%", size: 5, opacity: 0.38, delay: "3s", duration: "19s" },
    { top: "52%", left: "64%", size: 6, opacity: 0.42, delay: "4s", duration: "21s" },
    { top: "62%", left: "28%", size: 4, opacity: 0.32, delay: "5s", duration: "22s" },
    { top: "72%", left: "88%", size: 4, opacity: 0.34, delay: "1.5s", duration: "23s" },
    { top: "82%", left: "48%", size: 6, opacity: 0.4, delay: "2.5s", duration: "17s" },
    { top: "90%", left: "18%", size: 5, opacity: 0.3, delay: "3.5s", duration: "24s" },
    { top: "24%", left: "92%", size: 4, opacity: 0.28, delay: "4.5s", duration: "26s" },
  ];

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(245,158,11,0.18),transparent_60%)]" />
      {dots.map((dot, index) => (
        <span
          key={`${dot.left}-${dot.top}-${index}`}
          className="absolute rounded-full bg-amber-300/70 blur-[1px]"
          style={{
            top: dot.top,
            left: dot.left,
            width: `${dot.size}px`,
            height: `${dot.size}px`,
            opacity: dot.opacity,
            animation: `sparkleFloat ${dot.duration} ease-in-out infinite`,
            animationDelay: dot.delay,
          }}
        />
      ))}
    </div>
  );
};

export default SparkleBackground;
