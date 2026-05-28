// examples/debug_scenario.sv
// Debug 场景：一个简单的数据通路 + 控制逻辑
// 假设 debug 发现 pipeline_data 的值异常

module debug_demo (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  data_a,
    input  wire [7:0]  data_b,
    input  wire [1:0]  sel,
    input  wire        en,
    output reg  [7:0]  result,
    output reg         flag
);

    // 内部信号
    reg [7:0] mux_out;
    reg [7:0] pipeline_data;
    reg [7:0] processed;
    reg       valid;

    // MUX 选择
    always @(*) begin
        case (sel)
            2'b00: mux_out = data_a;
            2'b01: mux_out = data_b;
            2'b10: mux_out = data_a + data_b;
            2'b11: mux_out = data_a - data_b;
        endcase
    end

    // 流水线寄存器
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pipeline_data <= 8'h00;
            valid <= 1'b0;
        end else if (en) begin
            pipeline_data <= mux_out;
            valid <= 1'b1;
        end else begin
            valid <= 1'b0;
        end
    end

    // 数据处理
    always @(*) begin
        if (valid)
            processed = pipeline_data + 8'h01;
        else
            processed = 8'h00;
    end

    // 输出
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result <= 8'h00;
            flag <= 1'b0;
        end else begin
            result <= processed;
            flag <= (pipeline_data > 8'hF0);
        end
    end

endmodule
