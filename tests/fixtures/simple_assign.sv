module simple_assign (
    input logic clk,
    input logic rst_n,
    input logic input_a,
    input logic input_b,
    output logic wire_out,
    output logic reg_out
);
    assign wire_out = input_a & input_b;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            reg_out <= 1'b0;
        else
            reg_out <= wire_out;
    end
endmodule