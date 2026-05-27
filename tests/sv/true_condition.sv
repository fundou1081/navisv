// ============================================================
// true_condition.sv
// 测试 true_condition 提取
// ============================================================

module true_condition (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [1:0]  sel,
    input  logic [7:0]  a,
    input  logic [7:0]  b,
    input  logic [7:0]  c,
    input  logic        cond,
    output logic [7:0]  out_if,
    output logic [7:0]  out_case,
    output logic [7:0]  out_tern,
    output logic [7:0]  out_nested
);

    // ----------------------------------------------------------
    // 1. 简单 if/else
    // ----------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            out_if <= 8'd0;
        else if (sel == 2'b00)
            out_if <= a;
        else if (sel == 2'b01)
            out_if <= b;
        else
            out_if <= c;
    end

    // ----------------------------------------------------------
    // 2. case 语句
    // ----------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            out_case <= 8'd0;
        else case (sel)
            2'b00: out_case <= a;
            2'b01: out_case <= b;
            2'b10: out_case <= c;
            default: out_case <= 8'd0;
        endcase
    end

    // ----------------------------------------------------------
    // 3. 三元运算符 (组合)
    // ----------------------------------------------------------
    assign out_tern = cond ? a : b;

    // ----------------------------------------------------------
    // 4. 嵌套 if
    // ----------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            out_nested <= 8'd0;
        else if (sel[1])
            if (sel[0])
                out_nested <= a;
            else
                out_nested <= b;
        else
            out_nested <= c;
    end

endmodule
