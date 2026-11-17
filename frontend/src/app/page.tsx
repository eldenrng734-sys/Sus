export default function Home() {
  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <section className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-10 md:py-16">
        <nav className="flex items-center justify-between rounded-full border border-slate-200 bg-white/80 px-5 py-3 shadow-sm backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-500 text-sm font-bold text-white">
              S
            </div>
            <div>
              <p className="text-sm font-semibold tracking-[0.2em] text-slate-500 uppercase">
                Sales Assist
              </p>
            </div>
          </div>

          <div className="hidden items-center gap-8 text-sm font-medium text-slate-600 md:flex">
            <a href="#features" className="transition hover:text-slate-900">
              Features
            </a>
            <a href="#insights" className="transition hover:text-slate-900">
              Insights
            </a>
            <a href="#pricing" className="transition hover:text-slate-900">
              Pricing
            </a>
          </div>

          <button className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700">
            Start free
          </button>
        </nav>

        <div className="grid items-center gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6">
            <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700">
              Built for modern revenue teams
            </span>

            <h1 className="max-w-xl text-4xl font-bold tracking-tight text-slate-900 md:text-6xl">
              Turn every sales conversation into momentum.
            </h1>

            <p className="max-w-lg text-lg leading-8 text-slate-600">
              Sales Assist helps your team capture opportunities, prioritize follow-ups,
              and stay on top of every deal with AI-powered guidance.
            </p>

            <div className="flex flex-col gap-4 sm:flex-row">
              <button className="rounded-full bg-emerald-500 px-6 py-3 text-base font-semibold text-white shadow-lg shadow-emerald-200 transition hover:bg-emerald-600">
                Book a demo
              </button>
              <button className="rounded-full border border-slate-300 bg-white px-6 py-3 text-base font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50">
                View dashboard
              </button>
            </div>

            <div className="flex items-center gap-6 pt-2 text-sm text-slate-500">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                24/7 pipeline visibility
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                3x faster follow-up
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-200/60">
            <div className="rounded-2xl bg-slate-900 p-5 text-white">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-300">Quarterly pipeline</p>
                  <h2 className="mt-1 text-3xl font-bold">$2.4M</h2>
                </div>
                <div className="rounded-full bg-emerald-500/20 px-3 py-1 text-sm font-medium text-emerald-300">
                  +18.4%
                </div>
              </div>

              <div className="space-y-4">
                {[
                  { label: 'Qualified leads', value: '318', width: 'w-3/4' },
                  { label: 'Demo bookings', value: '92', width: 'w-2/3' },
                  { label: 'Conversions', value: '41%', width: 'w-2/5' },
                ].map((item) => (
                  <div key={item.label}>
                    <div className="mb-2 flex items-center justify-between text-sm text-slate-300">
                      <span>{item.label}</span>
                      <span>{item.value}</span>
                    </div>
                    <div className="h-2.5 rounded-full bg-slate-700">
                      <div className={`h-2.5 rounded-full bg-emerald-400 ${item.width}`} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-4">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-sm text-slate-500">Win rate</p>
                <p className="mt-2 text-2xl font-bold text-slate-900">68%</p>
              </div>
              <div className="rounded-2xl bg-emerald-50 p-4">
                <p className="text-sm text-emerald-700">Forecast</p>
                <p className="mt-2 text-2xl font-bold text-emerald-900">94%</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

