// 自动生成: data_out 的 true_condition 覆盖
// 条件路径数: 10

covergroup cg_data_out_conditions @(posedge clk);

    // 条件信号: en
    cp_en: coverpoint en;

    // 条件信号: err_flag
    cp_err_flag: coverpoint err_flag;

    // 条件信号: mode
    cp_mode: coverpoint mode;

    // 条件信号: priority_level
    cp_priority_level: coverpoint priority_level;

    // 条件信号: rst_n
    cp_rst_n: coverpoint rst_n;

    // 路径 1: data_out = 8'd0
    // true_condition: !(rst_n)

    // 路径 2: data_out = data_in Add 8'd1
    // true_condition: rst_n && en && mode == 2'b0 && !(err_flag) && priority_level > 3'b11

    // 路径 3: data_out = data_in
    // true_condition: rst_n && en && mode == 2'b0 && !(err_flag) && !(priority_level > 3'b11)

    // 路径 4: data_out = 8'd254
    // true_condition: rst_n && en && mode == 2'b0 && err_flag

    // 路径 5: data_out = data_in Subtract 8'd1
    // true_condition: rst_n && en && !(mode == 2'b0) && mode == 2'b1 && !(err_flag)

    // 路径 6: data_out = 8'd255
    // true_condition: rst_n && en && !(mode == 2'b0) && mode == 2'b1 && err_flag

    // 路径 7: data_out = data_in LogicalShiftLeft 1
    // true_condition: rst_n && en && !(mode == 2'b0) && !(mode == 2'b1) && mode == 2'b10 && priority_level > 3'b101

    // 路径 8: data_out = data_in LogicalShiftRight 1
    // true_condition: rst_n && en && !(mode == 2'b0) && !(mode == 2'b1) && mode == 2'b10 && !(priority_level > 3'b101)

    // 路径 9: data_out = data_in
    // true_condition: rst_n && en && !(mode == 2'b0) && !(mode == 2'b1) && !(mode == 2'b10)

    // 路径 10: data_out = 8'd0
    // true_condition: rst_n && !(en)

    // 交叉覆盖
    cx_all: cross cp_en, cp_err_flag, cp_mode, cp_priority_level;
endgroup