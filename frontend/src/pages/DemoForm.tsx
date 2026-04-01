const DemoForm = () => {
  return (
    <div className="min-h-screen bg-black text-[#f5f5f5] px-4 py-10">
      <div className="max-w-xl mx-auto bg-[#111111] border border-[#2a2a2a] rounded-2xl p-6 md:p-8">
        <h1 className="text-2xl md:text-3xl font-heading font-bold mb-6 text-[#f59e0b]">Loan Demo Form</h1>

        <form className="space-y-4">
          <div>
            <label htmlFor="fullName" className="block text-sm mb-1 text-[#9ca3af]">Full Name</label>
            <input id="fullName" name="full_name" aria-label="Full Name" placeholder="Full Name" type="text" className="w-full rounded-xl bg-[#171717] border border-[#2a2a2a] px-4 py-3 outline-none focus:border-[#f59e0b]" />
          </div>

          <div>
            <label htmlFor="phone" className="block text-sm mb-1 text-[#9ca3af]">Phone</label>
            <input id="phone" name="phone" aria-label="Phone" placeholder="Phone Number" type="text" className="w-full rounded-xl bg-[#171717] border border-[#2a2a2a] px-4 py-3 outline-none focus:border-[#f59e0b]" />
          </div>

          <div>
            <label htmlFor="aadhaar" className="block text-sm mb-1 text-[#9ca3af]">Aadhaar</label>
            <input id="aadhaar" name="aadhaar_number" aria-label="Aadhaar Number" placeholder="Aadhaar Number" type="text" className="w-full rounded-xl bg-[#171717] border border-[#2a2a2a] px-4 py-3 outline-none focus:border-[#f59e0b]" />
          </div>

          <div>
            <label htmlFor="income" className="block text-sm mb-1 text-[#9ca3af]">Income</label>
            <input id="income" name="annual_income" aria-label="Annual Income" placeholder="Annual Income" type="text" className="w-full rounded-xl bg-[#171717] border border-[#2a2a2a] px-4 py-3 outline-none focus:border-[#f59e0b]" />
          </div>

          <div>
            <label htmlFor="landHolding" className="block text-sm mb-1 text-[#9ca3af]">Land Holding (Acres)</label>
            <input
              id="landHolding"
              name="land_holding_acres"
              aria-label="Land Holding (Acres)"
              placeholder="Land Holding (Acres)"
              type="text"
              className="w-full rounded-xl bg-[#171717] border border-[#2a2a2a] px-4 py-3 outline-none focus:border-[#f59e0b]"
            />
          </div>

          <div>
            <label htmlFor="farmerId" className="block text-sm mb-1 text-[#9ca3af]">Farmer ID</label>
            <input
              id="farmerId"
              name="farmer_id"
              aria-label="Farmer ID"
              placeholder="Farmer ID"
              type="text"
              className="w-full rounded-xl bg-[#171717] border border-[#2a2a2a] px-4 py-3 outline-none focus:border-[#f59e0b]"
            />
          </div>

          <button type="button" className="w-full mt-3 rounded-xl bg-[#f59e0b] text-black font-semibold px-4 py-3">Submit</button>
        </form>
      </div>
    </div>
  );
};

export default DemoForm;
