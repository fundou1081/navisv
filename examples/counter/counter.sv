// elk_counter.sv - minimal counter for elkjs exporter unit tests
// Used by tests/test_elk_exporter.py
module counter (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       enable,
    output logic [3:0] count
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 4'h0;
        else if (enable)
            count <= count + 4'h1;
    end
endmodule