// examples/nested_conditions.sv
// 场景5: 复杂嵌套 if 条件 → true_condition → coverage
//
// 信号 data_out 受到 4 层嵌套 if 条件控制
// navisv 将自动提取所有 true_condition 并生成 coverage

module nested_conditions (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  data_in,
    input  wire [1:0]  mode,
    input  wire        en,
    input  wire        err_flag,
    input  wire [2:0]  priority_level,
    output reg  [7:0]  data_out
);

    // 复杂嵌套条件逻辑
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 8'h00;
        end else if (en) begin                    // 第1层: en
            if (mode == 2'b00) begin              // 第2层: mode==0
                if (!err_flag) begin               // 第3层: !err_flag
                    if (priority_level > 3'd3) begin // 第4层: priority>3
                        data_out <= data_in + 8'h01;
                    end else begin
                        data_out <= data_in;
                    end
                end else begin
                    data_out <= 8'hFE;  // error path
                end
            end else if (mode == 2'b01) begin     // 第2层: mode==1
                if (!err_flag) begin               // 第3层: !err_flag
                    data_out <= data_in - 8'h01;
                end else begin
                    data_out <= 8'hFF;
                end
            end else if (mode == 2'b10) begin     // 第2层: mode==2
                if (priority_level > 3'd5) begin   // 第3层: priority>5
                    data_out <= data_in << 1;
                end else begin
                    data_out <= data_in >> 1;
                end
            end else begin                         // 第2层: mode==3
                data_out <= ~data_in;
            end
        end else begin
            data_out <= 8'h00;  // !en path
        end
    end

endmodule
